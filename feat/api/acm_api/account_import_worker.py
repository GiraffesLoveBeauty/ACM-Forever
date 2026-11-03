"""One bounded parsing job. Receives a private path, emits only bounded JSON."""
import json
import sys
from pathlib import Path


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    except ImportError:
        pass  # Windows uses byte/structure limits and parent-enforced process termination.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from acm_api.account_import_excel import ExcelError, MAX_FILE_BYTES, parse_workbook
    try:
        with open(sys.argv[1], "rb") as source:
            content = source.read(MAX_FILE_BYTES + 1)
        rows = parse_workbook(content)
        result = {"rows": rows}
    except ExcelError as exc:
        result = {"error": str(exc), "code": exc.code}
    except Exception:
        result = {"error": "无法解析该工作簿，请重新下载模板。", "code": "invalid_workbook"}
    encoded = json.dumps(result, ensure_ascii=True)
    if len(encoded) > 1024 * 1024:
        encoded = json.dumps({"error": "解析结果超过限制。", "code": "resource_limit"})
    print(encoded)


if __name__ == "__main__":
    main()
