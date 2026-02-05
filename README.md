# FastBank

FastBank is a backend-driven digital banking simulation built with FastAPI. It demonstrates real-world backend workflows such as account management, transactions, loan applications, approval flows, notifications, and real-time updates.


---

## Tech Stack

- FastAPI
- Python
- Async SQLAlchemy
- WebSockets
- Background Tasks
- PostgreSQL

---

## Project Setup (using uv)

1. Create and activate a virtual environment
```  
   uv venv  
   source .venv/bin/activate  
```

2. Install dependencies  
```
   uv sync  
```

3. Run the application  
```
   uvicorn app.main:app --reload  
```

---

## API Documentation

- Swagger UI: http://127.0.0.1:8000/docs  
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json
