.PHONY: help install migrate run test lint docker-build docker-up clean

help:
	@echo "Usage:"
	@echo "  make install       Install Python dependencies"
	@echo "  make migrate       Run database migrations"
	@echo "  make run           Start development server"
	@echo "  make test          Run tests with coverage"
	@echo "  make lint          Run linters (ruff + flake8)"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-up     Start all services with docker-compose"
	@echo "  make clean         Remove __pycache__ and .pyc files"

install:
	pip install --upgrade pip
	pip install -r requirements.txt

migrate:
	python manage.py migrate --noinput

run:
	python manage.py runserver 0.0.0.0:8000

test:
	python -m pytest tests/ -v --cov=backend --cov-report=term-missing

lint:
	ruff check backend/ scripts/ --ignore=E501,F403,F401
	flake8 backend/ scripts/ --max-line-length=120 --ignore=E402,F401,W503

docker-build:
	docker build -t medical-ai-system .

docker-up:
	docker-compose up -d --build

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

precommit:
	pre-commit run --all-files
