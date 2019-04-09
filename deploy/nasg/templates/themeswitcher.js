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
    var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
    /* user wants == mql match => remove storage */
    if ((mode == DEFAULT_THEME && !mql.matches) || (mode == ALT_THEME && mql.matches)) {
        localStorage.removeItem(STORAGE_KEY);
    }
    else {
        if(confirm("I\'ll need to store your choice in your browser, in a place called localStorage.\n\nAre you OK with this?")) {
            localStorage.setItem(STORAGE_KEY, mode);
        }
    }
    autoTheme(mql);
}

function autoTheme(e) {
    var mode = DEFAULT_THEME;
    try {
        var current = localStorage.getItem(STORAGE_KEY);
    } catch(e) {
        var current = DEFAULT_THEME;
    }
    if ( current != null) {
        mode = current;
    }
    else if (e.matches) {
        mode = ALT_THEME;
    }
    applyTheme(mode);
    indicateTheme(mode);
}

var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');
autoTheme(mql);
mql.addListener(autoTheme);

var test = 'ping';
try {
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    for(var i = colorscheme.length; i--; ) {
        colorscheme[i].onclick = setTheme;
    }
    var themeforms = document.getElementsByClassName(STORAGE_KEY);
    for(var i = themeforms.length; i--; ) {
        themeforms[i].style.display = 'inline-block';
    }
} catch(e) {
    console.log('localStorage is not available, manual theme switching is disabled');
}
