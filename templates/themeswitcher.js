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
        localStorage.setItem(STORAGE_KEY, mode);
    }
    autoTheme(mql);
}

function autoTheme(e) {
    var mode = DEFAULT_THEME;
    var current = localStorage.getItem(STORAGE_KEY);
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

for(var i = colorscheme.length; i--; ) {
    colorscheme[i].onclick = setTheme;
}

var themeforms = document.getElementsByClassName(STORAGE_KEY);
for(var i = themeforms.length; i--; ) {
    themeforms[i].style.display = 'inline-block';
}

function kcl(cb) {
  var input = '';
  var key = '38384040373937396665';
  document.addEventListener('keydown', function (e) {
    input += ("" + e.keyCode);
    if (input === key) {
      return cb();
    }
    if (!key.indexOf(input)) return;
    input = ("" + e.keyCode);
  });
}

kcl(function () {
    var e = document.createElement('img');
    e.src = '/iddqd.gif';
    document.body.appendChild(e);
})
