var DEFAULT_THEME = 'dark';
var ALT_THEME = 'light';
var STORAGE_KEY = 'theme';
var colorscheme = document.getElementsByName('colorscheme');

function setTheme(e) {
    var mode = e.target.value;
    if (mode == 'auto') {
        localStorage.removeItem(STORAGE_KEY);
    }
    else {
        localStorage.setItem(STORAGE_KEY, mode);
    }
    applyTheme(mode);
}

function applyTheme(mode) {
    var st = document.getElementById('css_alt');
    if (mode == ALT_THEME) {
        st.setAttribute('media', 'all');
    }
    else {
        st.setAttribute('media', 'speech');
    }

    for(var i = colorscheme.length; i--; ) {
        if(colorscheme[i].value == mode) {
            colorscheme[i].checked = true;
        }
    }
}

function mqlTheme(e) {
    if (localStorage.getItem(STORAGE_KEY) != null) {
        return false;
    }
    if (e.matches) {
        applyTheme(ALT_THEME);
    }
    else {
        applyTheme(DEFAULT_THEME);
    }
}

var current = localStorage.getItem(STORAGE_KEY);
if (current == null) { current = 'auto'; }
applyTheme(current);

var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
mql.addListener(mqlTheme);
for(var i = colorscheme.length; i--; ) {
    colorscheme[i].onclick = setTheme;
}

var themeforms = document.getElementsByClassName(STORAGE_KEY);
for(var i = themeforms.length; i--; ) {
    themeforms[i].style.display = 'inline-block';
}
