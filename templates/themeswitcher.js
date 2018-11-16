var DEFAULT_THEME = 'dark';
var ALT_THEME = 'light';
var STORAGE_KEY = 'theme';
var colorscheme = document.getElementsByName('colorscheme');

function indicateTheme(mode) {
    for(var i = colorscheme.length; i--; ) {
        if(colorscheme[i].value == mode) {
            colorscheme[i].checked = true;
        }
    }
}

function applyTheme(mode) {
    var st = document.getElementById('css_alt');
    if (mode == ALT_THEME) {
        st.setAttribute('media', 'all');
    }
    else {
        st.setAttribute('media', 'speech');
    }
}

function setTheme(e) {
    var mode = e.target.value;
    if (mode == 'auto') {
        localStorage.removeItem(STORAGE_KEY);
    }
    else {
        localStorage.setItem(STORAGE_KEY, mode);
    }
    var e = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
    autoTheme(e);
}

function autoTheme(e) {
    var current = localStorage.getItem(STORAGE_KEY);
    var mode = 'auto';
    var indicate = 'auto';
    if ( current != null) {
        indicate = mode = current;
    }
    else if (e.matches) {
        mode = ALT_THEME;
    }
    applyTheme(mode);
    indicateTheme(indicate);
}

var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
autoTheme(mql);
mql.addListener(autoTheme);

for(var i = colorscheme.length; i--; ) {
    colorscheme[i].onclick = setTheme;
}

var themeforms = document.getElementsByClassName(STORAGE_KEY);
for(var i = themeforms.length; i--; ) {
    themeforms[i].style.display = 'inline-block';
}
