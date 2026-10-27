import os, tempfile

# Must run before `app.config` is imported: isolate data and force a known configuration.
os.environ["RAG_DATA_DIR"] = tempfile.mkdtemp(prefix="rag-test-")
for var in ("APP_PASSWORD", "OPENAI_API_KEY", "GEMINI_API_KEY", "ORG_NAME", "AUTHOR_INFO",
            "BRAND_LOGO_HEADER", "BRAND_LOGO_FOOTER_LIGHT", "BRAND_LOGO_FOOTER_DARK"):
    os.environ[var] = ""
