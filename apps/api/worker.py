"""Reserved worker entrypoint; document ingestion is synchronous in DEV_MODE."""
if __name__ == "__main__":
    print("StudyAgent worker ready (DEV_MODE ingestion runs inline)")

