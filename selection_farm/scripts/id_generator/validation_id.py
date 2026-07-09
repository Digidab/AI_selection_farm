try:
    from .core import generate_id
except ImportError:
    from scripts.id_generator.core import generate_id


def issue_validation_id() -> str:
    return generate_id("VA00")


if __name__ == "__main__":
    print(issue_validation_id())
