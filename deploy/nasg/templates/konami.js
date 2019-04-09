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
