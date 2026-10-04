"""不依赖 Docker 守护进程的部署预检；不能代替实际镜像构建与容器启动。"""

from pathlib import Path
import yaml


def main():
    config = yaml.safe_load(Path("compose.yaml").read_text("utf-8"))
    assert set(config["services"]) == {"db", "migrate", "app"}
    app = config["services"]["app"]
    assert app["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert app["ports"] == ["127.0.0.1:8000:8000"]
    assert "POSTGRES_PASSWORD:?" in Path("compose.yaml").read_text("utf-8")
    for name in [".env", "data", "profiles", ".git"]:
        assert name in Path(".dockerignore").read_text("utf-8").splitlines()
    assert "python:3.12-" in Path("Dockerfile").read_text("utf-8")
    print("Compose structure / startup order / context exclusions: OK; container execution not checked")


if __name__ == "__main__":
    main()
