<?php

$db = new SQLite3('./search.sqlite', SQLITE3_OPEN_READONLY);
$q = str_replace('-', '+', $_GET['q']);
$sql = $db->prepare("
    SELECT
        url, category, title, snippet(data, '', '', '[...]', 5, 24), mtime
    FROM
        data
    WHERE
        data MATCH :q
    ORDER BY
        category
");
$sql->bindValue(':q', $q);
$query = $sql->execute();
$results = array();
if($query) {
    while ($row = $query->fetchArray(SQLITE3_ASSOC)) {
        array_push($results, $row);
    }
}

foreach ($results as $row) {
    $item_node = $channel_node->appendChild($xml->createElement("item"));
    $title_node = $item_node->appendChild($xml->createElement("title", $row['title']));
    $link_node = $item_node->appendChild($xml->createElement("link", $row['url']));
    $guid_link = $xml->createElement("guid", $row['url']);
    $guid_link->setAttribute("isPermaLink","true");
    $guid_node = $item_node->appendChild($guid_link);
    $description_node = $item_node->appendChild($xml->createElement("description"));
    $description_contents = $xml->createCDATASection(htmlentities($row["snippet(data, '', '', '[...]', 5, 24)"]));
    $description_node->appendChild($description_contents);
    $date_rfc = gmdate(DATE_RFC2822, $row['mtime']);
    $pub_date = $xml->createElement("pubDate", $date_rfc);
    $pub_date_node = $item_node->appendChild($pub_date);
}

header('Content-Type: text/xml; charset=utf-8', true);

$xml = new DOMDocument("1.0", "UTF-8");
$xml->preserveWhiteSpace = false;
$xml->formatOutput = true;

$rss = $xml->createElement("rss");
$rss_node = $xml->appendChild($rss);
$rss_node->setAttribute("version","2.0");


$rss_node->setAttribute("xmlns:dc","http://a9.com/-/spec/opensearch/1.1/");

$channel = $xml->createElement("channel");
$channel_node = $rss_node->appendChild($channel);

$channel_node->appendChild($xml->createElement("title", "Search results for: {$_GET['q']}"));
$channel_node->appendChild($xml->createElement("link", "{{ site.url }}"));
$channel_node->appendChild($xml->createElement("description", "Search {{ site.name }} for {$_GET['q']}"));

$channel_node->appendChild($xml->createElement("openSearch:totalResults", sizeof($results)));
$channel_node->appendChild($xml->createElement("openSearch:startIndex", 1));
$channel_node->appendChild($xml->createElement("openSearch:itemsPerPage", sizeof($results)));

$build_date = gmdate(DATE_RFC2822, time());
$channel_node->appendChild($xml->createElement("lastBuildDate", $build_date));

echo $xml->saveXML();
