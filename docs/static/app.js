(() => {
  "use strict";

  const SUPPORTED_LANGUAGES = ["fr", "en", "zh", "ar"];
  const LANGUAGE_STORAGE_KEY = "pixopdf.language";
  const THEME_STORAGE_KEY = "pixopdf.theme";
  const DEFAULT_LANGUAGE = "fr";
  const RELEASES_URL = "https://github.com/PixoGlace/pixopdf/releases";
  const DEFAULT_RELEASE_API =
    "https://api.github.com/repos/PixoGlace/pixopdf/releases/latest";

  const LANGUAGE_NAMES = {
    fr: "Français",
    en: "English",
    zh: "中文",
    ar: "العربية",
  };

  const RELEASE_FALLBACK_MESSAGES = {
    fr: "Aucun téléchargement direct n’est disponible pour le moment. Consultez la page des versions.",
    en: "No direct download is available yet. Visit the releases page.",
    zh: "目前没有可用的直接下载。请查看版本发布页面。",
    ar: "لا يتوفر تنزيل مباشر حاليًا. يمكنك زيارة صفحة الإصدارات.",
  };

  const scriptElement =
    document.currentScript ||
    document.querySelector('script[src$="/app.js"], script[src$="app.js"]');

  const state = {
    dictionary: {},
    language: DEFAULT_LANGUAGE,
    theme: "light",
    themeFollowsSystem: true,
    release: null,
    releaseState: "idle",
    releaseRequest: null,
  };

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // The interface remains functional when storage is blocked or unavailable.
    }
  }

  function normalizeLanguage(value) {
    if (typeof value !== "string") {
      return null;
    }

    const normalized = value.trim().toLowerCase().replace("_", "-");
    if (!normalized) {
      return null;
    }

    const base = normalized.split("-")[0];
    return SUPPORTED_LANGUAGES.includes(base) ? base : null;
  }

  function languageFromNavigator() {
    const preferences = Array.isArray(navigator.languages)
      ? navigator.languages
      : [navigator.language];

    for (const preference of preferences) {
      const language = normalizeLanguage(preference);
      if (language) {
        return language;
      }
    }

    return null;
  }

  function languageFromQuery() {
    try {
      return normalizeLanguage(new URL(window.location.href).searchParams.get("lang"));
    } catch {
      return null;
    }
  }

  function initialLanguage() {
    return (
      languageFromQuery() ||
      normalizeLanguage(readStorage(LANGUAGE_STORAGE_KEY)) ||
      languageFromNavigator() ||
      DEFAULT_LANGUAGE
    );
  }

  function dictionaryFor(language) {
    const source =
      state.dictionary.languages ||
      state.dictionary.translations ||
      state.dictionary;
    const localized = source?.[language];
    return localized && typeof localized === "object" ? localized : {};
  }

  function lookupIn(source, key) {
    if (!source || typeof source !== "object") {
      return null;
    }

    if (typeof source[key] === "string") {
      return source[key];
    }

    const nested = key
      .split(".")
      .reduce(
        (value, segment) =>
          value && typeof value === "object" ? value[segment] : undefined,
        source,
      );
    return typeof nested === "string" ? nested : null;
  }

  function translate(key, language = state.language) {
    if (!key) {
      return null;
    }

    return (
      lookupIn(dictionaryFor(language), key) ||
      lookupIn(dictionaryFor(DEFAULT_LANGUAGE), key)
    );
  }

  function interpolate(value, variables = {}) {
    return value.replace(/\{([a-zA-Z0-9_.-]+)\}/g, (match, key) => {
      const replacement = variables[key];
      return replacement === undefined || replacement === null
        ? match
        : String(replacement);
    });
  }

  function elementVariables(element) {
    const variables = {};
    for (const [name, value] of Object.entries(element.dataset)) {
      if (name.startsWith("i18nVar") && name.length > 7) {
        const key = `${name[7].toLowerCase()}${name.slice(8)}`;
        variables[key] = value;
      }
    }
    return variables;
  }

  function parseAttributeBindings(specification) {
    if (!specification) {
      return [];
    }

    const trimmed = specification.trim();
    if (trimmed.startsWith("{")) {
      try {
        const parsed = JSON.parse(trimmed);
        return Object.entries(parsed).filter(
          ([attribute, key]) =>
            typeof attribute === "string" && typeof key === "string",
        );
      } catch {
        return [];
      }
    }

    return trimmed
      .split(/[;,]/)
      .map((binding) => {
        const separator = binding.indexOf(":");
        if (separator < 1) {
          return null;
        }
        return [
          binding.slice(0, separator).trim(),
          binding.slice(separator + 1).trim(),
        ];
      })
      .filter(
        (binding) =>
          binding &&
          binding[0] &&
          binding[1] &&
          !/^on/i.test(binding[0]),
      );
  }

  function applyTranslations(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((element) => {
      const value = translate(element.dataset.i18n);
      if (value === null) {
        return;
      }

      const translated = interpolate(value, elementVariables(element));
      if (
        element instanceof HTMLInputElement &&
        ["button", "reset", "submit"].includes(element.type)
      ) {
        element.value = translated;
      } else {
        element.textContent = translated;
      }
    });

    root
      .querySelectorAll("[data-i18n-attr], [data-i18n-attrs]")
      .forEach((element) => {
        const specification =
          element.dataset.i18nAttr || element.dataset.i18nAttrs;
        const variables = elementVariables(element);

        for (const [attribute, key] of parseAttributeBindings(specification)) {
          const value = translate(key);
          if (value !== null) {
            element.setAttribute(attribute, interpolate(value, variables));
          }
        }
      });

    const title = translate("meta.title");
    if (title) {
      document.title = title;
      document
        .querySelectorAll(
          'meta[property="og:title"], meta[name="twitter:title"]',
        )
        .forEach((meta) => meta.setAttribute("content", title));
    }

    const description = translate("meta.description");
    if (description) {
      document
        .querySelectorAll(
          'meta[name="description"], meta[property="og:description"], meta[name="twitter:description"]',
        )
        .forEach((meta) => meta.setAttribute("content", description));
    }

    if (!state.release) {
      const message = translate("hero.release");
      if (message) {
        releaseElements("[data-release-note]").forEach((element) => {
          setDirectTextPreservingChildren(element, message);
        });
      }
    }

    if (state.releaseState === "fallback") {
      releaseElements("[data-release-fallback]").forEach((element) => {
        element.textContent = fallbackMessage();
      });
    }
  }

  function languageDirection(language) {
    const configured = translate("locale.dir", language);
    return configured === "rtl" || configured === "ltr"
      ? configured
      : language === "ar"
        ? "rtl"
        : "ltr";
  }

  function languageDisplayName(language) {
    return (
      translate("locale.name", language) ||
      translate("locale.label", language) ||
      LANGUAGE_NAMES[language]
    );
  }

  function languageOptions() {
    return document.querySelectorAll(
      "[data-lang-option], .language-menu [hreflang]",
    );
  }

  function syncLanguageControls() {
    document
      .querySelectorAll(
        "[data-lang-current], .language-menu summary span:not(.sr-only)",
      )
      .forEach((label) => {
        label.textContent = languageDisplayName(state.language);
      });

    languageOptions().forEach((option) => {
      const optionLanguage = normalizeLanguage(
        option.dataset.langOption || option.getAttribute("hreflang"),
      );
      const selected = optionLanguage === state.language;

      if (selected) {
        option.setAttribute("aria-current", "page");
      } else {
        option.removeAttribute("aria-current");
      }

      if (option.matches("button, [role='button']")) {
        option.setAttribute("aria-pressed", String(selected));
      }
    });
  }

  function updateLanguageInUrl(language) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("lang", language);
      window.history.replaceState(window.history.state, "", url);
    } catch {
      // Static content still changes when history manipulation is unavailable.
    }
  }

  function announceLanguageChange() {
    const status = document.querySelector("[data-language-status]");
    if (status) {
      status.textContent =
        translate("language.changed") || languageDisplayName(state.language);
    }

    document.dispatchEvent(
      new CustomEvent("pixopdf:languagechange", {
        detail: { language: state.language, direction: document.documentElement.dir },
      }),
    );
  }

  function setLanguage(
    requestedLanguage,
    { persist = true, updateUrl = true, announce = true } = {},
  ) {
    const language = normalizeLanguage(requestedLanguage);
    if (!language) {
      return false;
    }

    state.language = language;
    document.documentElement.lang =
      translate("locale.lang", language) || language;
    document.documentElement.dir = languageDirection(language);
    document.documentElement.dataset.language = language;

    if (persist) {
      writeStorage(LANGUAGE_STORAGE_KEY, language);
    }
    if (updateUrl) {
      updateLanguageInUrl(language);
    }

    applyTranslations();
    syncLanguageControls();
    syncThemeControls();

    if (state.release) {
      setReleaseMetadata(state.release);
    }

    if (announce) {
      announceLanguageChange();
    }
    return true;
  }

  function closeLanguageMenus(except = null) {
    document
      .querySelectorAll("details[data-language-menu], details.language-menu")
      .forEach((menu) => {
        if (menu !== except) {
          menu.open = false;
        }
      });
  }

  function bindLanguageControls() {
    languageOptions().forEach((option) => {
      option.addEventListener("click", (event) => {
        const language = normalizeLanguage(
          option.dataset.langOption || option.getAttribute("hreflang"),
        );
        if (!language) {
          return;
        }

        event.preventDefault();
        setLanguage(language);
        closeLanguageMenus();
        option
          .closest("details")
          ?.querySelector("summary")
          ?.focus({ preventScroll: true });
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }

      const openMenu = document.querySelector(
        "details[data-language-menu][open], details.language-menu[open]",
      );
      if (openMenu) {
        openMenu.open = false;
        openMenu.querySelector("summary")?.focus({ preventScroll: true });
      }
    });

    document.addEventListener("pointerdown", (event) => {
      if (!(event.target instanceof Node)) {
        return;
      }

      document
        .querySelectorAll(
          "details[data-language-menu][open], details.language-menu[open]",
        )
        .forEach((menu) => {
          if (!menu.contains(event.target)) {
            menu.open = false;
          }
        });
    });

    window.addEventListener("popstate", () => {
      const language = languageFromQuery();
      if (language) {
        setLanguage(language, { updateUrl: false, announce: false });
      }
    });
  }

  function preferredSystemTheme() {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function normalizeTheme(value) {
    return value === "dark" || value === "light" ? value : null;
  }

  function themeControls() {
    return document.querySelectorAll("[data-theme-toggle], #theme-toggle");
  }

  function syncThemeControls() {
    themeControls().forEach((control) => {
      const isDark = state.theme === "dark";

      if (control instanceof HTMLInputElement) {
        control.checked = isDark;
      } else if (!control.matches("label")) {
        control.setAttribute("aria-pressed", String(isDark));
      }

      const labelKey = isDark
        ? control.dataset.themeLightLabel || "controls.themeLight"
        : control.dataset.themeDarkLabel || "controls.themeDark";
      const label = translate(labelKey);
      if (label) {
        control.setAttribute("aria-label", label);
        control.setAttribute("title", label);
        control
          .querySelector?.("[data-theme-label]")
          ?.replaceChildren(document.createTextNode(label));
      }
    });
  }

  function setTheme(theme, { persist = true } = {}) {
    const normalized = normalizeTheme(theme);
    if (!normalized) {
      return false;
    }

    state.theme = normalized;
    state.themeFollowsSystem = !persist;
    document.documentElement.dataset.theme = normalized;
    document.documentElement.style.colorScheme = normalized;

    if (persist) {
      writeStorage(THEME_STORAGE_KEY, normalized);
    }

    syncThemeControls();
    document.dispatchEvent(
      new CustomEvent("pixopdf:themechange", {
        detail: { theme: normalized },
      }),
    );
    return true;
  }

  function bindThemeControls() {
    const savedTheme = normalizeTheme(readStorage(THEME_STORAGE_KEY));
    setTheme(savedTheme || preferredSystemTheme(), { persist: Boolean(savedTheme) });

    themeControls().forEach((control) => {
      if (control instanceof HTMLInputElement) {
        control.addEventListener("change", () => {
          setTheme(control.checked ? "dark" : "light");
        });
        return;
      }

      // A label linked to the existing checkbox already has native behavior.
      if (
        control instanceof HTMLLabelElement &&
        control.htmlFor &&
        document.getElementById(control.htmlFor) instanceof HTMLInputElement
      ) {
        return;
      }

      control.addEventListener("click", () => {
        setTheme(state.theme === "dark" ? "light" : "dark");
      });
    });

    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    media?.addEventListener?.("change", () => {
      if (state.themeFollowsSystem) {
        setTheme(preferredSystemTheme(), { persist: false });
      }
    });
  }

  function revealContent() {
    const elements = Array.from(document.querySelectorAll("[data-reveal]"));
    if (!elements.length) {
      return;
    }

    elements.forEach((element) => {
      const delay = Number.parseInt(element.dataset.revealDelay || "0", 10);
      if (Number.isFinite(delay) && delay >= 0) {
        element.style.setProperty("--reveal-delay", `${Math.min(delay, 2000)}ms`);
      }
      element.dataset.revealState = "pending";
    });

    const reduceMotion = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (reduceMotion || !("IntersectionObserver" in window)) {
      elements.forEach((element) => {
        element.classList.add("is-revealed");
        element.dataset.revealState = "visible";
      });
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }

          entry.target.classList.add("is-revealed");
          entry.target.dataset.revealState = "visible";
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -48px", threshold: 0.12 },
    );

    elements.forEach((element) => observer.observe(element));
  }

  function detectedPlatform() {
    const platform = [
      navigator.userAgentData?.platform,
      navigator.platform,
      navigator.userAgent,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (/mac|darwin|os x/.test(platform)) {
      return "macos";
    }
    if (/win/.test(platform)) {
      return "windows";
    }
    if (/linux|x11|ubuntu|debian|fedora/.test(platform)) {
      return "linux";
    }
    return null;
  }

  const PLATFORM_MATCHERS = {
    macos: {
      platform: [/\bmac(?:os)?\b/i, /\bdarwin\b/i, /\bosx\b/i, /\buniversal\b/i],
      native: [/\.dmg$/i, /\.pkg$/i],
      archive: [/\.zip$/i, /\.tar\.gz$/i],
    },
    windows: {
      platform: [/\bwindows\b/i, /\bwin(?:32|64)?\b/i],
      native: [/\.msi$/i, /\.exe$/i, /\.msix$/i],
      archive: [/\.zip$/i],
    },
    linux: {
      platform: [
        /\blinux\b/i,
        /\bubuntu\b/i,
        /\bdebian\b/i,
        /\bfedora\b/i,
        /\bappimage\b/i,
      ],
      native: [/\.appimage$/i, /\.deb$/i, /\.rpm$/i],
      archive: [/\.tar\.gz$/i, /\.tar\.xz$/i, /\.zip$/i],
    },
  };

  function validDownloadUrl(value) {
    try {
      return new URL(value).protocol === "https:";
    } catch {
      return false;
    }
  }

  function scoreAsset(asset, platform) {
    const matcher = PLATFORM_MATCHERS[platform];
    if (!matcher || typeof asset?.name !== "string") {
      return Number.NEGATIVE_INFINITY;
    }
    if (!validDownloadUrl(asset.browser_download_url)) {
      return Number.NEGATIVE_INFINITY;
    }

    const name = asset.name;
    if (
      /(?:checksums?|sha(?:256|512)?|symbols?|debug|source|\.asc$|\.sig$)/i.test(
        name,
      )
    ) {
      return Number.NEGATIVE_INFINITY;
    }

    const platformMatches = matcher.platform.filter((pattern) =>
      pattern.test(name),
    ).length;
    const nativeIndex = matcher.native.findIndex((pattern) => pattern.test(name));
    const archiveIndex = matcher.archive.findIndex((pattern) =>
      pattern.test(name),
    );
    const hasNativeExtension = nativeIndex >= 0;
    const hasArchiveExtension = archiveIndex >= 0;

    if (!platformMatches && !hasNativeExtension) {
      return Number.NEGATIVE_INFINITY;
    }

    let score = platformMatches * 20;
    if (hasNativeExtension) {
      score += 12 - nativeIndex;
    } else if (hasArchiveExtension) {
      score += 5 - archiveIndex;
    }
    if (/universal|x86_64|amd64|arm64|aarch64/i.test(name)) {
      score += 1;
    }
    return score;
  }

  function assetForPlatform(assets, platform) {
    return assets
      .map((asset) => ({ asset, score: scoreAsset(asset, platform) }))
      .filter(({ score }) => Number.isFinite(score))
      .sort((left, right) => right.score - left.score)[0]?.asset;
  }

  function releaseElements(selector) {
    return document.querySelectorAll(selector);
  }

  function setDirectTextPreservingChildren(element, message) {
    const messageTarget = element.querySelector("[data-release-note-text]");
    if (messageTarget) {
      messageTarget.textContent = message;
      return;
    }

    const visibleTextNode = Array.from(element.childNodes).find(
      (node) => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim(),
    );
    if (visibleTextNode) {
      visibleTextNode.nodeValue = ` ${message}`;
    } else {
      element.append(document.createTextNode(` ${message}`));
    }
  }

  function setReleaseMetadata(release) {
    const version = String(release.tag_name || release.name || "").trim();
    const name = String(release.name || release.tag_name || "").trim();

    releaseElements("[data-release-version]").forEach((element) => {
      element.textContent = version;
    });
    releaseElements("[data-release-name]").forEach((element) => {
      element.textContent = name;
    });
    releaseElements("[data-release-note]").forEach((element) => {
      element.dataset.resolvedReleaseVersion = version;
      const templateKey = element.dataset.releaseNote;
      const template =
        translate(templateKey) ||
        translate("release.available") ||
        translate("download.available");
      const message = template
        ? interpolate(template, { name, version })
        : `${name || version} · GitHub`;
      setDirectTextPreservingChildren(element, message);
    });
  }

  function fallbackMessage() {
    return (
      translate("release.fallbackDetail") ||
      translate("release.unavailable") ||
      translate("download.unavailable") ||
      RELEASE_FALLBACK_MESSAGES[state.language]
    );
  }

  function setFallbackVisibility(visible) {
    releaseElements("[data-release-fallback]").forEach((element) => {
      element.hidden = !visible;
      if (visible) {
        element.textContent = fallbackMessage();
        if (!element.hasAttribute("role")) {
          element.setAttribute("role", "status");
        }
        element.setAttribute("aria-live", "polite");
      }
    });
  }

  function fallbackDescriptionId() {
    const fallback = document.querySelector("[data-release-fallback]");
    if (!fallback) {
      return null;
    }
    if (!fallback.id) {
      fallback.id = "release-download-fallback";
    }
    return fallback.id;
  }

  function setFallbackDescription(element, enabled) {
    const fallbackId = fallbackDescriptionId();
    if (!fallbackId) {
      return;
    }

    const ids = new Set(
      (element.getAttribute("aria-describedby") || "")
        .split(/\s+/)
        .filter(Boolean),
    );
    if (enabled) {
      ids.add(fallbackId);
    } else {
      ids.delete(fallbackId);
    }

    if (ids.size) {
      element.setAttribute("aria-describedby", Array.from(ids).join(" "));
    } else {
      element.removeAttribute("aria-describedby");
    }
  }

  function setReleaseState(value) {
    state.releaseState = value;
    document.documentElement.dataset.releaseState = value;
    releaseElements("[data-release-root]").forEach((element) => {
      element.dataset.releaseState = value;
    });
  }

  function fallbackDownloads(releaseUrl = RELEASES_URL) {
    state.release = null;
    releaseElements("[data-download-platform]").forEach((element) => {
      if (element instanceof HTMLAnchorElement) {
        element.href = releaseUrl;
        element.removeAttribute("download");
        element.removeAttribute("aria-disabled");
      } else if (
        element instanceof HTMLButtonElement ||
        element instanceof HTMLInputElement
      ) {
        element.disabled = true;
      }
      element.dataset.downloadState = "fallback";
      element.classList.remove("is-ready");
      element.classList.add("is-pending");
      setFallbackDescription(element, true);
      element.removeAttribute("aria-busy");
    });
    setFallbackVisibility(true);
    setReleaseState("fallback");
  }

  function applyRelease(release) {
    const assets = Array.isArray(release.assets) ? release.assets : [];
    const releaseUrl = validDownloadUrl(release.html_url)
      ? release.html_url
      : RELEASES_URL;
    let available = 0;
    let missing = 0;

    setReleaseMetadata(release);

    releaseElements("[data-download-platform]").forEach((element) => {
      const requested = element.dataset.downloadPlatform;
      const platform = requested === "auto" ? detectedPlatform() : requested;
      const asset = platform ? assetForPlatform(assets, platform) : null;

      element.dataset.resolvedPlatform = platform || "unknown";
      element.removeAttribute("aria-busy");

      if (asset) {
        if (element instanceof HTMLAnchorElement) {
          element.href = asset.browser_download_url;
        }
        element.dataset.downloadState = "ready";
        element.dataset.releaseAsset = asset.name;
        element.dataset.downloadVersion = release.tag_name || release.name || "";
        element.removeAttribute("aria-disabled");
        element.classList.remove("is-pending");
        element.classList.add("is-ready");
        setFallbackDescription(element, false);
        available += 1;
      } else {
        if (element instanceof HTMLAnchorElement) {
          element.href = releaseUrl;
          element.removeAttribute("download");
          element.removeAttribute("aria-disabled");
        } else if (
          element instanceof HTMLButtonElement ||
          element instanceof HTMLInputElement
        ) {
          element.disabled = true;
        }
        element.dataset.downloadState = "fallback";
        element.classList.remove("is-ready");
        element.classList.add("is-pending");
        setFallbackDescription(element, true);
        missing += 1;
      }
    });

    setFallbackVisibility(missing > 0);
    setReleaseState(available > 0 ? (missing > 0 ? "partial" : "ready") : "fallback");
  }

  function releaseApiUrl() {
    const configured =
      scriptElement?.dataset.releaseApi ||
      document.documentElement.dataset.releaseApi ||
      DEFAULT_RELEASE_API;

    try {
      const url = new URL(configured, document.baseURI);
      return url.protocol === "https:" ? url.href : DEFAULT_RELEASE_API;
    } catch {
      return DEFAULT_RELEASE_API;
    }
  }

  async function loadLatestRelease() {
    const controls = releaseElements("[data-download-platform]");
    if (!controls.length && !document.querySelector("[data-release-version]")) {
      return;
    }

    setReleaseState("loading");
    controls.forEach((element) => element.setAttribute("aria-busy", "true"));

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);

    try {
      const response = await fetch(releaseApiUrl(), {
        headers: {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`GitHub releases request failed (${response.status})`);
      }

      const release = await response.json();
      if (!release || typeof release !== "object" || !release.tag_name) {
        throw new Error("GitHub returned no usable release");
      }

      state.release = release;
      applyRelease(release);
    } catch {
      fallbackDownloads();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function dictionaryUrl() {
    const configured = scriptElement?.dataset.i18nSrc;
    if (configured) {
      return new URL(configured, document.baseURI).href;
    }
    if (scriptElement?.src) {
      return new URL("translations.json", scriptElement.src).href;
    }
    return new URL("static/translations.json", document.baseURI).href;
  }

  async function loadDictionary() {
    try {
      const response = await fetch(dictionaryUrl(), {
        headers: { Accept: "application/json" },
        cache: "force-cache",
      });
      if (!response.ok) {
        throw new Error(`Translations request failed (${response.status})`);
      }

      const dictionary = await response.json();
      if (!dictionary || typeof dictionary !== "object") {
        throw new Error("Translations payload is invalid");
      }

      state.dictionary = dictionary;
      document.documentElement.dataset.i18nState = "ready";
      setLanguage(state.language, {
        persist: false,
        updateUrl: false,
        announce: false,
      });
    } catch {
      document.documentElement.dataset.i18nState = "fallback";
      syncLanguageControls();
    }
  }

  function initialize() {
    document.documentElement.classList.add("has-js");
    state.language = initialLanguage();
    document.documentElement.lang = state.language;
    document.documentElement.dir = state.language === "ar" ? "rtl" : "ltr";
    document.documentElement.dataset.language = state.language;
    if (languageFromQuery()) {
      writeStorage(LANGUAGE_STORAGE_KEY, state.language);
    }

    bindLanguageControls();
    bindThemeControls();
    syncLanguageControls();
    revealContent();

    state.releaseRequest = loadLatestRelease();
    void loadDictionary();
  }

  window.PixoPDFSite = Object.freeze({
    get language() {
      return state.language;
    },
    get theme() {
      return state.theme;
    },
    setLanguage,
    setTheme,
    refreshRelease: loadLatestRelease,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
