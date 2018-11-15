var DEFAULT_THEME = 'dark';
var ALT_THEME = 'light';

function setTheme(mode) {
    var st = document.querySelector('#css_alt');
    var cb = document.querySelector('#contrast');
    if (mode == DEFAULT_THEME) {
        st.setAttribute("media", "speech");
        cb.checked = true;
    }
    else {
        st.setAttribute("media", "all");
        cb.checked = false;
    }
}

function toggleTheme(e) {
    var mode = DEFAULT_THEME;
    if (e.checked == false) {
        mode = ALT_THEME;
    }
    setTheme(mode);
    localStorage.setItem("theme", mode);
    return true;
}

function mqlTheme(e) {
    console.log(e);
    if (e.matches) {
        setTheme(ALT_THEME);
    }
    else {
        setTheme(DEFAULT_THEME);
    }
}

var theme = localStorage.getItem("theme");
if (theme != null) {
    setTheme(theme);
}
else {
    var mql = window.matchMedia("(prefers-color-scheme: " + ALT_THEME + ")");
    if(mql.matches) {
        setTheme(ALT_THEME);
    }
    mql.addListener(mqlTheme);
}
