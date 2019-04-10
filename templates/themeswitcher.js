var DEFAULT_THEME = 'dark';
var ALT_THEME = 'light';
var STORAGE_KEY = 'theme';
var colorscheme = [];
var mql = window.matchMedia('(prefers-color-scheme: ' + ALT_THEME + ')');

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

function doTheme() {
    var themeform = document.createElement('form');
    themeform.className = "theme";
    themeform.innerHTML='<svg width="16" height="16"><use xlink:href="#icon-contrast"></use></svg>';
    document.getElementById("header-forms").insertBefore(themeform, document.getElementById("search"));
    var schemes = ["dark", "light"];
    for (var i = 0; i < schemes.length; i++) {
        var span = document.createElement('span');
        themeform.appendChild(span);

        var input = document.createElement('input');
        input.name = 'colorscheme';
        input.type = 'radio';
        input.id = schemes[i] + input.name;
        input.value = schemes[i];
        span.appendChild(input);

        var label = document.createElement('label');
        label.htmlFor = input.id;
        label.innerHTML = schemes[i];
        span.appendChild(label);
    }

    colorscheme = document.getElementsByName('colorscheme');
    for(var i = colorscheme.length; i--; ) {
        colorscheme[i].onclick = setTheme;
    }

    autoTheme(mql);
    mql.addListener(autoTheme);
}

var test = 'ping';
try {
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    doTheme();
} catch(e) {
    console.log('localStorage is not available, manual theme switching is disabled');
}
