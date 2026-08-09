.DEFAULT_GOAL := help

POETRY ?= poetry
DOCS_DIR ?= docs
APP := PixoPDF
APP_ID := pixopdf
APP_VERSION = $(shell $(POETRY) run python -c "from pixopdf.config import VERSION; print(VERSION)")
UNAME_S := $(shell uname -s 2>/dev/null || echo Windows)
UNAME_M := $(shell uname -m 2>/dev/null || echo unknown)
ARCH := $(UNAME_M)
RELEASE_DIR := release

ifeq ($(OS),Windows_NT)
	PLATFORM := windows
	ARCH := x86_64
else ifeq ($(UNAME_S),Darwin)
	PLATFORM := macos
else
	PLATFORM := linux
endif

DEB_ARCH := $(ARCH)
ifeq ($(ARCH),x86_64)
	DEB_ARCH := amd64
else ifeq ($(ARCH),aarch64)
	DEB_ARCH := arm64
endif

.PHONY: help install install-all lock update run test coverage lint format format-check typecheck check build packaging-assets package package-macos package-windows package-linux release-current clean docs-dev docs-check

help: ## Afficher les commandes disponibles
	@awk 'BEGIN {FS = ":.*##"; printf "Utilisation : make <commande>\n\n"} /^[a-zA-Z_-]+:.*?##/ {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Créer l'environnement Poetry et installer les dépendances de développement
	$(POETRY) install --with dev

install-all: ## Installer aussi les outils de build et les fonctionnalités optionnelles
	$(POETRY) install --with dev,build --extras "ocr"

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

packaging-assets: ## Générer les icônes et illustrations des installateurs
	$(POETRY) run python packaging/create_packaging_art.py

build: packaging-assets ## Générer le paquet Python et l'application PyInstaller
	$(POETRY) install --with build
	$(POETRY) build
	$(POETRY) run pyinstaller --clean --noconfirm pixopdf.spec

package: ## Créer le portable et l'installateur natif de l'OS courant
ifeq ($(PLATFORM),macos)
	$(MAKE) package-macos
else ifeq ($(PLATFORM),windows)
	$(MAKE) package-windows
else
	$(MAKE) package-linux
endif

package-macos: packaging-assets
	@test -d "dist/$(APP).app"
	rm -rf "build/dmg-stage"
	mkdir -p "$(RELEASE_DIR)" "build/dmg-stage"
	rm -f "$(RELEASE_DIR)/$(APP)-macos-$(ARCH)-portable.zip" "$(RELEASE_DIR)/$(APP)-macos-$(ARCH).dmg"
	ditto -c -k --sequesterRsrc --keepParent "dist/$(APP).app" "$(RELEASE_DIR)/$(APP)-macos-$(ARCH)-portable.zip"
	cp -R "dist/$(APP).app" "build/dmg-stage/$(APP).app"
	@if command -v create-dmg >/dev/null 2>&1; then \
		create-dmg --volname "$(APP)" --volicon "assets/$(APP).icns" \
			--background "assets/dmg/pixopdf-dmg-background.png" \
			--window-pos 200 120 --window-size 660 420 --text-size 13 \
			--icon-size 112 --icon "$(APP).app" 128 255 \
			--hide-extension "$(APP).app" --app-drop-link 515 255 \
			--hdiutil-quiet --no-internet-enable \
			"$(RELEASE_DIR)/$(APP)-macos-$(ARCH).dmg" "build/dmg-stage"; \
	else \
		ln -sfn /Applications "build/dmg-stage/Applications"; \
		hdiutil create -volname "$(APP)" -srcfolder "build/dmg-stage" -ov -format UDZO \
			"$(RELEASE_DIR)/$(APP)-macos-$(ARCH).dmg"; \
	fi
	hdiutil verify "$(RELEASE_DIR)/$(APP)-macos-$(ARCH).dmg"

package-windows: packaging-assets
	mkdir -p "$(RELEASE_DIR)"
	$(POETRY) run python -m zipfile -c "$(RELEASE_DIR)/$(APP)-windows-x86_64-portable.zip" "dist/$(APP)"
	PIXO_APP_NAME="$(APP)" PIXO_APP_VERSION="$(APP_VERSION)" PIXO_SOURCE_DIR="$(CURDIR)/dist/$(APP)" PIXO_OUTPUT_DIR="$(CURDIR)/$(RELEASE_DIR)" PIXO_ROOT_DIR="$(CURDIR)" PIXO_WIZARD_IMAGE="$(CURDIR)/build/packaging/windows-wizard.bmp" PIXO_WIZARD_SMALL_IMAGE="$(CURDIR)/build/packaging/windows-small.bmp" iscc packaging/windows/PixoPDF.iss

package-linux: packaging-assets
	rm -rf "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable" "$(RELEASE_DIR)/deb-root"
	mkdir -p "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable"
	cp "dist/$(APP)" "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable/$(APP)"
	cp "packaging/linux/pixopdf.desktop" "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable/"
	cp "assets/$(APP).png" "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable/pixopdf.png"
	cp "LICENSE" "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable/"
	tar -C "$(RELEASE_DIR)" -czf "$(RELEASE_DIR)/$(APP)-linux-$(ARCH)-portable.tar.gz" "$(APP)-linux-$(ARCH)-portable"
	mkdir -p "$(RELEASE_DIR)/deb-root/DEBIAN" "$(RELEASE_DIR)/deb-root/opt/$(APP)" "$(RELEASE_DIR)/deb-root/usr/bin" "$(RELEASE_DIR)/deb-root/usr/share/applications" "$(RELEASE_DIR)/deb-root/usr/share/icons/hicolor/256x256/apps" "$(RELEASE_DIR)/deb-root/usr/share/metainfo"
	cp "dist/$(APP)" "$(RELEASE_DIR)/deb-root/opt/$(APP)/$(APP)"
	chmod 755 "$(RELEASE_DIR)/deb-root/opt/$(APP)/$(APP)"
	ln -sfn "/opt/$(APP)/$(APP)" "$(RELEASE_DIR)/deb-root/usr/bin/$(APP)"
	cp "packaging/linux/pixopdf.desktop" "$(RELEASE_DIR)/deb-root/usr/share/applications/pixopdf.desktop"
	cp "assets/$(APP).png" "$(RELEASE_DIR)/deb-root/usr/share/icons/hicolor/256x256/apps/pixopdf.png"
	cp "packaging/linux/io.github.pixoglace.pixopdf.metainfo.xml" "$(RELEASE_DIR)/deb-root/usr/share/metainfo/io.github.pixoglace.pixopdf.metainfo.xml"
	printf '%s\n' 'Package: pixopdf' 'Version: $(APP_VERSION)' 'Section: utils' 'Priority: optional' 'Architecture: $(DEB_ARCH)' 'Maintainer: PixoGlace' 'Homepage: https://github.com/PixoGlace/pixopdf' 'Description: Organize, transform and protect PDF documents locally' > "$(RELEASE_DIR)/deb-root/DEBIAN/control"
	dpkg-deb --root-owner-group --build "$(RELEASE_DIR)/deb-root" "$(RELEASE_DIR)/pixopdf_$(APP_VERSION)_$(DEB_ARCH).deb"

release-current: check build package ## Tester puis créer les deux formats pour l'OS courant

docs-dev: ## Servir la vitrine statique localement sur le port 8000
	$(POETRY) run python -m http.server 8000 --directory $(DOCS_DIR)

docs-check: ## Vérifier la page unique, les traductions, les liens et les assets
	$(POETRY) run pytest tests/unit/test_docs_site.py

clean: ## Supprimer les artefacts et caches locaux
	rm -rf build dist release .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
