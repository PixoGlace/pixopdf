.DEFAULT_GOAL := help

POETRY ?= poetry

.PHONY: help install install-all lock update run test coverage lint format format-check typecheck check build clean

help: ## Afficher les commandes disponibles
	@awk 'BEGIN {FS = ":.*##"; printf "Utilisation : make <commande>\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Créer l'environnement Poetry et installer les dépendances de développement
	$(POETRY) install --with dev

install-all: ## Installer aussi les outils de build et les fonctionnalités optionnelles
	$(POETRY) install --with dev,build --extras "signatures ocr"

lock: ## Régénérer poetry.lock sans mettre à jour les versions résolues
	$(POETRY) lock

update: ## Mettre à jour les dépendances et poetry.lock
	$(POETRY) update

run: ## Lancer PixoPDF dans l'environnement Poetry
	$(POETRY) run pixopdf

test: ## Exécuter les tests
	$(POETRY) run pytest

coverage: ## Exécuter les tests avec la couverture
	$(POETRY) run pytest --cov=pixopdf --cov-report=term-missing --cov-fail-under=80

lint: ## Vérifier le code avec Ruff
	$(POETRY) run ruff check .

format: ## Formater le code avec Ruff
	$(POETRY) run ruff format .

format-check: ## Vérifier le formatage sans modifier les fichiers
	$(POETRY) run ruff format --check .

typecheck: ## Vérifier le typage statique
	$(POETRY) run mypy src

check: lint format-check typecheck coverage ## Exécuter tous les contrôles

build: ## Générer le paquet Python et l'application PyInstaller
	$(POETRY) install --with build
	$(POETRY) build
	$(POETRY) run pyinstaller --clean --noconfirm pixopdf.spec

clean: ## Supprimer les artefacts et caches locaux
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
