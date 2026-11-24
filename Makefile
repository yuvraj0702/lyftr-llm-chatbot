.PHONY: up down test

up:
	docker compose up --build -d
	@echo Frontend: http://localhost:3000  Backend: http://localhost:8000/health

down:
	docker compose down

test:
	cd backend && python -m pytest -q
