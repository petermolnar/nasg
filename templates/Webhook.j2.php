<?php

function _syslog($msg) {
    $trace = debug_backtrace();
    $caller = $trace[1];
    $parent = $caller['function'];
    if (isset($caller['class']))
        $parent = $caller['class'] . '::' . $parent;

    return error_log( "{$parent}: {$msg}" );
}

$raw = file_get_contents("php://input");
try {
    $payload = json_decode($raw, TRUE);
}
catch (Exception $e) {
    header('HTTP/1.1 422 Unprocessable Entity');
    _syslog('[webhook] json_decode failed on:' . $raw);
    die('Unprocessable Entity');
}

if(isset($payload['secret']) && $payload['secret'] == '{{ webmentionio.secret }}' ) {
    $msg = sprintf('
Type: %s
Source: %s
Target: %s
From: %s

%s
',
    $payload['post']['wm-property'],
    $payload['source'],
    $payload['target'],
    $payload['post']['author']['name'],
    $payload['post']['content']['text']
    );

    _syslog('[webhook] accepted from webmention.io');
    mail("{{ author.email }}", "[webmention] {$payload['source']}", $msg);
    header('HTTP/1.1 202 Accepted');
    exit(0);
}

header('HTTP/1.1 400 Bad Request');
_syslog('[webhook] bad request:' . $raw);
die('Bad Request');
