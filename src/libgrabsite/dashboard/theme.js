/** Theme preference: "auto" follows the OS, "light" and "dark" override it. */
export const THEMES = ["auto", "light", "dark"];
const THEME_STORAGE_KEY = "grab-site-theme";

export const readStoredTheme = () => {
	try {
		const saved = localStorage.getItem(THEME_STORAGE_KEY);
		return THEMES.includes(saved) ? saved : "auto";
	} catch {
		// Storage is unavailable in some private windows and sandboxed frames.
		return "auto";
	}
};

export const writeStoredTheme = (theme) => {
	try {
		localStorage.setItem(THEME_STORAGE_KEY, theme);
	} catch {
		// The choice then lasts only until the page is reloaded.
	}
};
