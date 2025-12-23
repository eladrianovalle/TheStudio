from studio._runtime_removed import raise_runtime_removed


def run_crew_isolated():
    raise_runtime_removed("studio.crew_runner")


if __name__ == "__main__":
    try:
        sys.exit(run_crew_isolated())
    except Exception as e:
        import traceback
        error_output = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "phase": os.environ.get("STUDIO_PHASE", "market")
        }
        print("__STUDIO_RESULT_START__")
        print(json.dumps(error_output))
        print("__STUDIO_RESULT_END__")
        sys.exit(1)
