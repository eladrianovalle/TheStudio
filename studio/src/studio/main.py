#!/usr/bin/env python
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from studio.verdict import extract_verdict


REQUIRED_MODULES = {
    "email_validator": 'pip install "email-validator"',
}


def _apply_solo_mode() -> bool:
    """Disable heavy litellm proxy features when running locally."""
    solo_mode = os.environ.get("STUDIO_SOLO_MODE", "true").lower() not in {"false", "0", "no"}
    if solo_mode:
        env_defaults = {
            "LITELLM_LOGGING": "false",
            "LITELLM_PROXY_SERVER": "false",
            "LITELLM_SAVE_RAW_OUTPUT": "false",
            "LITELLM_LOG_DB_QUERIES": "false",
        }
        for key, value in env_defaults.items():
            os.environ.setdefault(key, value)
    return solo_mode


def _save_output(phase: str, result: str, inputs: dict, success: bool) -> Path:
    """Save crew output to timestamped markdown file."""
    output_dir = Path("output") / phase
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{phase}_{timestamp}.md"
    
    with open(output_file, 'w') as f:
        f.write(f"# Studio {phase.title()} Phase Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Status:** {'COMPLETED' if success else 'FAILED'}\n\n")
        
        f.write("## Input Parameters\n\n")
        for key, value in inputs.items():
            f.write(f"- **{key}:** {value}\n")
        
        f.write("\n## Crew Output\n\n")
        f.write(str(result))
        
        if success and phase != "studio":
            verdict = extract_verdict(str(result))
            f.write(f"\n\n## Final Verdict\n\n**{verdict}**\n")
        elif not success:
            f.write("\n\n> ⚠️ Report captured after an error. See stack trace above for details.\n")
    
    return output_file


def _run_health_checks() -> dict:
    """Validate required modules and API keys before running the crew."""
    missing = []
    for module, remedy in REQUIRED_MODULES.items():
        if importlib.util.find_spec(module) is None:
            missing.append(f"{module} → {remedy}")

    if missing:
        details = "\n  - ".join(missing)
        raise ImportError(
            "Preflight dependency check failed. Install the missing packages:\n"
            f"  - {details}"
        )

    model_name = os.environ.get("STUDIO_MODEL", "gemini-2.5-flash")
    provider = model_name.split("/", 1)[0].lower() if "/" in model_name else "gemini"
    provider_env_map = {
        "gemini": "GEMINI_API_KEY",
        "google": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    }

    api_env_var = provider_env_map.get(provider)
    api_key_present = bool(api_env_var and os.environ.get(api_env_var))
    if api_env_var and not api_key_present:
        raise EnvironmentError(
            f"Missing required environment variable: {api_env_var}. "
            "Set it in your shell or .env before running Studio."
        )

    return {
        "model": model_name,
        "provider_env": api_env_var or "N/A",
        "api_key_present": bool(api_key_present),
    }


def _run_crew_subprocess(phase: str, inputs: dict, solo_mode: bool) -> dict:
    """Run crew in isolated subprocess to prevent atexit crashes."""
    env_template = os.environ.copy()
    env_template["STUDIO_PHASE"] = phase
    
    # Pass inputs via environment
    if phase == "studio":
        env_template["STUDIO_OBJECTIVE"] = inputs.get("objective", "")
        env_template["STUDIO_BUDGET_CAP"] = inputs.get("budget_cap", "$0-20/mo")
    else:
        env_template["STUDIO_GAME_IDEA"] = inputs.get("game_idea", "")
    
    if solo_mode:
        env_template["STUDIO_SOLO_MODE"] = "true"
    
    cmd = [sys.executable, "-m", "studio.crew_runner"]
    attempts = []
    max_attempts = 2
    
    for attempt in range(1, max_attempts + 1):
        env = env_template.copy()
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                cwd=Path(__file__).parent.parent.parent
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            parsed = {
                "success": result.returncode == 0,
                "phase": phase,
                "inputs": inputs,
                "stderr": stderr,
                "attempt": attempt,
                "returncode": result.returncode,
            }

            marker_start = "__STUDIO_RESULT_START__"
            marker_end = "__STUDIO_RESULT_END__"
            if marker_start in stdout and marker_end in stdout:
                json_str = stdout.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
                parsed.update(json.loads(json_str))
            else:
                parsed["result"] = stdout.strip()

            if parsed.get("success"):
                return parsed

            attempts.append(parsed)
            if attempt < max_attempts:
                time.sleep(2 * attempt)  # backoff
                continue
            return parsed

        except subprocess.TimeoutExpired:
            timeout_result = {
                "success": False,
                "error": "Crew execution timed out after 10 minutes",
                "phase": phase,
                "attempt": attempt,
            }
            attempts.append(timeout_result)
            if attempt < max_attempts:
                continue
            return timeout_result
        except Exception as e:
            exception_result = {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "phase": phase,
                "attempt": attempt,
            }
            attempts.append(exception_result)
            if attempt < max_attempts:
                time.sleep(2 * attempt)
                continue
            return exception_result


def run():
    raise_runtime_removed("studio.main")
    phase = os.environ.get("STUDIO_PHASE", "market").lower()
    solo_mode = _apply_solo_mode()
    health = _run_health_checks()

    if phase == "studio":
        objective = os.environ.get(
            "STUDIO_OBJECTIVE",
            "How do we make Studio the best always-on cofounder for a solo dev with tiny capital and big ambitions?"
        )
        budget_cap = os.environ.get("STUDIO_BUDGET_CAP", "$0-20/mo")
        inputs = {
            'objective': objective,
            'budget_cap': budget_cap,
        }
    else:
        inputs = {
            'game_idea': os.environ.get(
                "STUDIO_GAME_IDEA",
                "A 3D stealth horror roguelike for the web"
            )
        }

    print(f"--- {phase.upper()} ROOM ---")
    if solo_mode:
        print(" Solo Mode active (litellm proxy/logging isolated in subprocess)")
    print(f" Health Check → Model: {health['model']} | API Key: {'OK' if health['api_key_present'] else 'N/A'}")

    # Run crew in subprocess for crash isolation
    result_data = _run_crew_subprocess(phase, inputs, solo_mode)
    
    if result_data["success"]:
        result = result_data["result"]
        output_file = _save_output(phase, result, inputs, success=True)
        
        print("\n\n--- FINAL OUTPUT ---")
        print(result)
        print(f"\n Report saved to: {output_file}")
        if result_data.get("attempt", 1) > 1:
            print(f"(Completed after {result_data['attempt']} attempts)")

        if phase != "studio":
            verdict = result_data.get("verdict") or extract_verdict(str(result))
            print(f"\n=== STUDIO VERDICT: {verdict} ===")
    else:
        error_msg = result_data.get("error", "Unknown error")
        error_trace = result_data.get("traceback", "No traceback available")
        stderr = result_data.get("stderr", "")
        
        error_report = (
            f"Studio run failed with error: {error_msg}\n\n"
            "```traceback\n"
            f"{error_trace}\n"
            "```\n\n"
            f"Stderr output:\n```\n{stderr}\n```"
        )
        output_file = _save_output(phase, error_report, inputs, success=False)
        print(f"\n Studio run aborted. Detailed error saved to {output_file}")
        print(f"Error: {error_msg}")
        sys.exit(1)


if __name__ == "__main__":
   run()