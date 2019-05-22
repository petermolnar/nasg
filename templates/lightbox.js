var links2img = []

function initLightbox() {
    var links = document.getElementsByTagName("a");
    for(var i = links.length; i--; ) {
        var imginside = links[i].getElementsByTagName("img");
        if (imginside.length == 1 ) {
            links2img.push(links[i])
            links[i].onclick = openLightbox;
        }
    }
}

function openLightbox(e) {
    var lightbox = document.createElement('div');
    lightbox.style.width = "100%";
    lightbox.style.height = "100%";
    lightbox.style.position = "fixed";
    lightbox.style.top = "0";
    lightbox.style.left = "0";
    lightbox.style.display = "table";
    lightbox.style.zIndex = "999";
    lightbox.style.backgroundColor = "rgba(0, 0, 0, 0.7)";
    lightbox.addEventListener('click', function(){
        closeLightbox(lightbox);
    });

    var fig = document.createElement('figure');
    fig.style.display = "table-cell";
    fig.style.align = "center";
    fig.style.verticalAlign = "middle";

    var img = document.createElement('img');
    img.src = e.target.parentNode.href;

    fig.appendChild(img);
    lightbox.appendChild(fig);

    var aroot = findLightboxroot(e.target);
    aroot.appendChild(lightbox);

    return false;
}

function findLightboxroot(e) {
    if (e.nodeName == "ARTICLE") {
        return e;
    }
    else {
        return findLightboxroot(e.parentNode);
    }
}

function closeLightbox(t) {
    t.parentNode.removeChild(t);
    return false;
}

initLightbox();
