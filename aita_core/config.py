from dataclasses import dataclass, field
import json
import os


INT_KEY_DICT_FIELDS = frozenset({
    "week_topics", "topic_num_to_week", "hw_num_to_week",
    "lab_num_to_week", "example_prompts",
})

EDITABLE_FIELDS = [
    "course_name", "course_short_name", "course_description",
    "system_prompt",
    "week_topics", "topic_num_to_week", "hw_num_to_week",
    "lab_num_to_week", "study_guide_to_week",
    "example_prompts",
    "textbook_url", "textbook_chapter_to_week",
    "llm_model", "llm_temperature", "retrieval_k",
    "chunk_size", "chunk_overlap", "embedding_model",
]


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

    def _overrides_path(self) -> str:
        return os.path.join(self.data_dir, "config_overrides.json")

    def load_overrides(self):
        """Load saved config overrides from JSON file in data_dir."""
        path = self._overrides_path()
        if not os.path.isfile(path):
            return
        with open(path) as f:
            overrides = json.load(f)
        for key, value in overrides.items():
            if hasattr(self, key) and key in EDITABLE_FIELDS:
                if key in INT_KEY_DICT_FIELDS and isinstance(value, dict):
                    value = {int(k): v for k, v in value.items()}
                setattr(self, key, value)

    def save_overrides(self, overrides: dict):
        """Save config overrides to JSON file and apply them in-memory."""
        for key, value in overrides.items():
            if hasattr(self, key) and key in EDITABLE_FIELDS:
                setattr(self, key, value)
        serializable = {}
        for key, value in overrides.items():
            if key in INT_KEY_DICT_FIELDS and isinstance(value, dict):
                serializable[key] = {str(k): v for k, v in value.items()}
            else:
                serializable[key] = value
        path = self._overrides_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(serializable, f, indent=2)


_config: CourseConfig | None = None


def set_config(config: CourseConfig):
    global _config
    _config = config
    _config.load_overrides()


def get_config() -> CourseConfig:
    if _config is None:
        raise RuntimeError("aita_core.set_config() must be called before use")
    return _config
