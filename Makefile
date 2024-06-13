test:
	pytest ./tests \
		--cov \
		--cov-report term \
		--cov-fail-under=65 \
		-vvv

flake:
	flake8 ./src ./tests --count --max-complexity=10 --max-line-length=127 --statistics

black:
	black ./src ./tests

isort:
	isort --profile black ./src ./tests
