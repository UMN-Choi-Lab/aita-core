from aita_core.config import CourseConfig, set_config, discover_google_oauth


def run(config: CourseConfig):
    """Start the AITA Streamlit app with the given course configuration."""
    set_config(config)
    from aita_core.app import main
    main()
