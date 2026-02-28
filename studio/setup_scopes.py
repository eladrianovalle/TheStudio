#!/usr/bin/env python3
"""
Interactive setup wizard for Studio scopes configuration.

Helps users create .studio/scopes.toml with sensible defaults.
"""
import sys
from pathlib import Path
from typing import List, Tuple


def get_studio_root() -> Path:
    """Get Studio root directory."""
    import os
    return Path(os.getenv("STUDIO_ROOT", Path.cwd()))


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    while True:
        response = input(f"{question} [{default_str}]: ").strip().lower()
        if not response:
            return default
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("Please answer 'y' or 'n'")


def prompt_int(question: str, default: int, min_val: int = 1) -> int:
    """Prompt user for integer input."""
    while True:
        response = input(f"{question} [{default}]: ").strip()
        if not response:
            return default
        try:
            value = int(response)
            if value < min_val:
                print(f"Please enter a value >= {min_val}")
                continue
            return value
        except ValueError:
            print("Please enter a valid number")


def prompt_text(question: str, default: str) -> str:
    """Prompt user for text input."""
    response = input(f"{question} [{default}]: ").strip()
    return response if response else default


def get_preset_scopes() -> List[Tuple[str, str, int]]:
    """Get preset scope configurations."""
    return [
        ("high_level", "Architecture, plans, strategic decisions", 4),
        ("implementation", "Detailed design, API contracts, core implementation", 2),
        ("polish", "Documentation, final review, minor refinements", 2),
    ]


def create_custom_scopes() -> List[Tuple[str, str, int]]:
    """Interactive creation of custom scopes."""
    scopes = []
    print("\nCreate custom scopes (enter blank name to finish):")
    
    while True:
        print(f"\nScope #{len(scopes) + 1}:")
        name = input("  Name (e.g., 'planning', 'coding', 'testing'): ").strip()
        if not name:
            break
        
        focus = input("  Focus (what this scope covers): ").strip()
        if not focus:
            focus = f"Work on {name}"
        
        max_iter = prompt_int("  Max iterations", default=2, min_val=1)
        
        scopes.append((name, focus, max_iter))
        
        if not prompt_yes_no("Add another scope?", default=False):
            break
    
    return scopes


def generate_scopes_toml(scopes: List[Tuple[str, str, int]]) -> str:
    """Generate TOML content for scopes."""
    lines = [
        "# Studio Scopes Configuration",
        "#",
        "# Defines iteration allocation across different work scopes.",
        "# Scopes are processed sequentially in the order defined.",
        "",
    ]
    
    for name, focus, max_iter in scopes:
        lines.extend([
            f"[scopes.{name}]",
            f'focus = "{focus}"',
            f"max_iterations = {max_iter}",
            "",
        ])
    
    return "\n".join(lines)


def main():
    """Run the setup wizard."""
    print("=" * 60)
    print("Studio Scopes Setup Wizard")
    print("=" * 60)
    print()
    print("This wizard will help you create .studio/scopes.toml")
    print("for scope-based iteration allocation.")
    print()
    
    studio_root = get_studio_root()
    studio_dir = studio_root / ".studio"
    scopes_file = studio_dir / "scopes.toml"
    
    # Check if file already exists
    if scopes_file.exists():
        print(f"⚠️  Scopes config already exists: {scopes_file}")
        if not prompt_yes_no("Overwrite existing configuration?", default=False):
            print("Setup cancelled.")
            return 1
        print()
    
    # Choose preset or custom
    print("Choose configuration type:")
    print("  1. Preset (recommended): high_level → implementation → polish")
    print("  2. Custom: define your own scopes")
    print()
    
    choice = input("Choice [1]: ").strip()
    
    if choice == "2":
        scopes = create_custom_scopes()
        if not scopes:
            print("\n❌ No scopes defined. Setup cancelled.")
            return 1
    else:
        # Use preset
        scopes = get_preset_scopes()
        print("\nUsing preset scopes:")
        for name, focus, max_iter in scopes:
            print(f"  • {name}: {max_iter} iterations - {focus}")
        print()
        
        # Allow customization
        if prompt_yes_no("Customize iteration counts?", default=False):
            print()
            custom_scopes = []
            for name, focus, _ in scopes:
                max_iter = prompt_int(f"  {name} max iterations", default=4 if name == "high_level" else 2)
                custom_scopes.append((name, focus, max_iter))
            scopes = custom_scopes
    
    # Generate and save
    toml_content = generate_scopes_toml(scopes)
    
    print("\n" + "=" * 60)
    print("Generated configuration:")
    print("=" * 60)
    print(toml_content)
    print("=" * 60)
    print()
    
    if not prompt_yes_no("Save this configuration?", default=True):
        print("Setup cancelled.")
        return 1
    
    # Create directory if needed
    studio_dir.mkdir(parents=True, exist_ok=True)
    
    # Write file
    scopes_file.write_text(toml_content, encoding="utf-8")
    
    print(f"\n✅ Scopes configuration saved to: {scopes_file}")
    print()
    print("Next steps:")
    print("  1. Run: python run_phase.py prepare --phase <phase> --text '<description>'")
    print("  2. Scopes will auto-load from .studio/scopes.toml")
    print("  3. Use --no-scopes to disable if needed")
    print()
    print("See docs/SCOPES_GUIDE.md for more information.")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
