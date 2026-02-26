from fastapi import FastAPI

app = FastAPI(title="Coding Challenge Yuno")


@app.get("/")
def root():
    return {"message": "Hello from Coding Challenge Yuno!"}


@app.get("/health")
def health():
    return {"status": "ok"}
