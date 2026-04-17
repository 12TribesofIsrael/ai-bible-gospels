"""Modal deployment for AI Bible Gospels unified web app."""
import modal

app = modal.App("ai-bible-gospels")
volume = modal.Volume.from_name("ai-bible-gospels-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.111.0",
        "uvicorn[standard]>=0.29.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.0",
        "requests>=2.31.0",
        "slowapi>=0.1.9",
    )
    .add_local_dir(
        "workflows/biblical-cinematic/server",
        remote_path="/app/workflows/biblical-cinematic/server",
    )
    .add_local_dir(
        "workflows/biblical-cinematic/text_processor",
        remote_path="/app/workflows/biblical-cinematic/text_processor",
    )
    .add_local_dir(
        "workflows/biblical-cinematic/assets",
        remote_path="/app/workflows/biblical-cinematic/assets",
    )
    .add_local_dir(
        "workflows/custom-script",
        remote_path="/app/workflows/custom-script",
    )
)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("ai-bible-gospels")],
    volumes={"/data": volume},
    scaledown_window=300,
    timeout=1800,
)
@modal.asgi_app()
def web():
    import sys
    import os

    sys.path.insert(0, "/app/workflows/biblical-cinematic/server")
    sys.path.insert(0, "/app/workflows/biblical-cinematic/text_processor")
    sys.path.insert(0, "/app/workflows/custom-script")

    os.chdir("/app/workflows/biblical-cinematic/server")
    os.environ.setdefault("DEPLOYED", "true")

    from app import app as fastapi_app
    return fastapi_app
