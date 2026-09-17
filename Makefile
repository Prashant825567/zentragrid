.PHONY: install dev test e2e demo routes clean

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run with no credentials at all (in-memory storage, fake tokens)
dev-memory:
	STORAGE_BACKEND=memory AUTH_ALLOW_INSECURE_TOKENS=true \
		uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

e2e:
	python scripts/e2e_real_test.py

demo:
	python scripts/demo_keep.py

routes:
	@python -c "from app.main import create_app; a=create_app(); \
		[print(f'{m:7} {r.path}') for r in a.routes if getattr(r,'methods',None) \
		 for m in sorted(r.methods-{'HEAD','OPTIONS'})]"

session:
	python scripts/generate_session.py

channels:
	python scripts/list_channels.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
