import os

ROOT_DIR = "/home/debifarm/Desktop/Project/AI_selection_farm/selection_farm"
SAVE_DIR = "/home/debifarm/Desktop/Project/AI_selection_farm/office/workshop/script_files"


def generate_structure(root_path, save_dir, prefix=""):
    def walk_dir(path, indent=""):
        entries = sorted(os.listdir(path))
        for i, entry in enumerate(entries):
            full_path = os.path.join(path, entry)
            is_last = (i == len(entries) - 1)
            pointer = "└── " if is_last else "├── "

            if os.path.isfile(full_path):
                icon = "📄 "
                lines.append(f"{indent}{pointer}{icon}{entry}")
            elif os.path.isdir(full_path):
                icon = "📁 "
                lines.append(f"{indent}{pointer}{icon}{entry}/")
                new_indent = indent + ("    " if is_last else "│   ")
                walk_dir(full_path, new_indent)

    lines = [f"{prefix}{os.path.basename(root_path)}/"]
    walk_dir(root_path)

    output_file = os.path.join(save_dir, "Structure.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Структура сохранена в: {output_file}")


if __name__ == "__main__":
    generate_structure(ROOT_DIR, SAVE_DIR)
