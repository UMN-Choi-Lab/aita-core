from dataclasses import dataclass, field


@dataclass
class CourseConfig:
    # Course identity
    course_id: str                                      # "3102"
    course_name: str                                    # "CEGE 3102: Uncertainty and Decision Analysis"
    course_short_name: str                              # "CEGE 3102 AITA"
    course_description: str                             # Shown on login page

    # Pedagogical system prompt (course-specific)
    system_prompt: str

    # Week/topic mappings
    week_topics: dict                                   # {1: ["topic1", ...], ...}
    topic_num_to_week: dict                             # slide/handout topic num -> week
    hw_num_to_week: dict                                # HW number -> week
    lab_num_to_week: dict                               # Lab number -> week
    study_guide_to_week: dict                           # "Quiz 1 " -> week
    example_prompts: dict                               # {1: ["prompt1", ...], ...}

    # Paths
    base_dir: str
    course_materials_dir: str
    faiss_db_dir: str
    docs_dir: str
    backup_dir: str
    data_dir: str

    # Auth
    admin_password: str
    cookie_name: str
    cookie_key: str
    redirect_uri: str
    google_client_secret_file: str = ""

    # Textbook (optional, for wikibook ingestion)
    textbook_url: str = ""
    textbook_chapter_to_week: dict = field(default_factory=dict)

    # LLM / embedding settings
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0
    chunk_size: int = 2048
    chunk_overlap: int = 256
    retrieval_k: int = 5

    @property
    def google_auth_enabled(self) -> bool:
        return bool(self.google_client_secret_file)

    @property
    def week_to_hw(self) -> dict:
        result = {}
        for hw, wk in self.hw_num_to_week.items():
            result[wk] = f"HW{hw}"
        return result

    def get_topics_covered(self, current_week):
        covered = []
        for week in range(1, current_week + 1):
            for topic in self.week_topics.get(week, []):
                if topic not in covered and "review" not in topic.lower():
                    covered.append(topic)
        return covered

    def get_topics_not_covered(self, current_week):
        covered = self.get_topics_covered(current_week)
        all_topics = []
        for week in range(1, 16):
            for topic in self.week_topics.get(week, []):
                if topic not in all_topics and "review" not in topic.lower():
                    all_topics.append(topic)
        return [t for t in all_topics if t not in covered]


_config: CourseConfig | None = None


def set_config(config: CourseConfig):
    global _config
    _config = config


def get_config() -> CourseConfig:
    if _config is None:
        raise RuntimeError("aita_core.set_config() must be called before use")
    return _config
