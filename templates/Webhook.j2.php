<?php

$raw = file_get_contents("php://input");
try {
  $payload = json_decode($raw, TRUE);
} catch (Exception $e) {
    header('HTTP/1.1 422 Unprocessable Entity');
    die('Unprocessable Entity');
}

if(! isset($payload['secret']) || $payload['secret'] != '{{ callback_secret }}' ) {
    header('HTTP/1.1 400 Bad Request');
    die('Bad Request');
}

mail("{{ author.email }}", "[webmention] {$payload['source']}", $raw);
header('HTTP/1.1 202 Accepted');
