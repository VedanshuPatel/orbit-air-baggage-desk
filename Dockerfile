# STRETCH GOAL 4
# Runs the tests by default. To run the app, pass main.py and its arguments:
#   docker run --rm orbit-air-baggage-desk main.py --help
FROM python:3.12-slim

WORKDIR /app

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

ENTRYPOINT ["python"]
CMD ["-m", "pytest"]
