from dataclasses import dataclass, field
import datetime
import json
import os
import re


INT_KEY_DICT_FIELDS = frozenset({
    "week_topics", "topic_num_to_week", "hw_num_to_week",
    "lab_num_to_week", "example_prompts",
})

EDITABLE_FIELDS = [
    "course_name", "course_short_name", "course_description",
    "system_prompt",
    "semester_start", "test_mode",
    "week_topics", "topic_num_to_week", "hw_num_to_week",
    "lab_num_to_week", "study_guide_to_week",
    "exam_scope",
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
    admin_emails: list = field(default_factory=list)  # Google emails that auto-get admin access
    google_client_secret_file: str = ""

    # Semester start date (ISO format, e.g. "2025-01-21") for auto-computing current week
    semester_start: str = ""

    # Test mode: when True, show week slider in chat sidebar for testing
    test_mode: bool = False

    # Exam scope (auto-detected or manually set)
    # Format: {"Midterm 1": {"week_start": 1, "week_end": 7}, ...}
    exam_scope: dict = field(default_factory=dict)

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

    def get_current_week(self) -> int:
        """Compute current week from today's date and semester_start.

        Returns 1 if semester_start is not set or date is before semester start.
        Clamps to max week in week_topics.
        """
        if not self.semester_start:
            return 1
        try:
            start = datetime.date.fromisoformat(self.semester_start)
        except ValueError:
            return 1
        today = datetime.date.today()
        if today < start:
            return 1
        week = (today - start).days // 7 + 1
        max_week = max(self.week_topics.keys()) if self.week_topics else 15
        return min(week, max_week)

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

    def auto_detect_exam_scope(self) -> dict:
        """Auto-detect exam scope from week_topics by finding review/exam weeks."""
        exam_weeks = []
        for week in sorted(self.week_topics.keys()):
            for topic in self.week_topics[week]:
                topic_lower = topic.lower()
                if "final" in topic_lower and ("review" in topic_lower or "exam" in topic_lower):
                    exam_weeks.append(("Final", week))
                elif "midterm" in topic_lower or ("exam" in topic_lower and "final" not in topic_lower):
                    match = re.search(r"(\d+)", topic_lower)
                    num = match.group(1) if match else "1"
                    exam_weeks.append((f"Midterm {num}", week))

        exam_weeks.sort(key=lambda x: x[1])

        exams = {}
        prev_end = 0
        for exam_name, exam_week in exam_weeks:
            if "final" in exam_name.lower():
                exams[exam_name] = {"week_start": 1, "week_end": exam_week - 1}
            else:
                exams[exam_name] = {
                    "week_start": prev_end + 1,
                    "week_end": exam_week - 1,
                }
                prev_end = exam_week

        # If only Midterm 1 and Final detected, infer Midterm 2 as the gap
        midterms = [n for n in exams if "midterm" in n.lower()]
        if len(midterms) == 1 and "Final" in exams:
            mt1_week = prev_end  # the midterm 1 review week
            final_end = exams["Final"]["week_end"]
            if final_end - mt1_week > 2:
                exams["Midterm 2"] = {
                    "week_start": mt1_week + 1,
                    "week_end": final_end,
                }

        return exams

    def get_exam_topics(self, exam_name: str) -> list:
        """Get the list of topics covered by a specific exam."""
        scope = self.exam_scope.get(exam_name, {})
        if not scope:
            return []
        week_start = scope.get("week_start", 1)
        week_end = scope.get("week_end", 15)
        topics = []
        for week in range(week_start, week_end + 1):
            for topic in self.week_topics.get(week, []):
                if topic not in topics and "review" not in topic.lower():
                    topics.append(topic)
        return topics

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
