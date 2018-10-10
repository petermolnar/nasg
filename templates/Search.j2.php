{% extends "base.j2.html" %}
{% block lang %}{% endblock %}
{% block title %}Search results for: <?php echo($_GET['q']); ?>{% endblock %}
{% block content %}
<main>
    <header>
        <h1>Search results for: <?php echo($_GET['q']); ?></h1>
    </header>
<?php
$db = new SQLite3('./search.sqlite', SQLITE3_OPEN_READONLY);
$q = str_replace('-', '+', $_GET['q']);
$sql = $db->prepare("
    SELECT
        url, category, title, snippet(data, '', '', '[...]', 5, 24)
    FROM
        data
    WHERE
        data MATCH :q
    ORDER BY
        category
");
$sql->bindValue(':q', $q);
$results = $sql->execute();

printf("<dl>");
while ($row = $results->fetchArray(SQLITE3_ASSOC)) {
    printf('<dt><a href="%s">%s</a></dt><dd>%s</dd>', $row['url'], $row['title'], $row["snippet(data, '', '', '[...]', 5, 24)"]);

}
printf("</dl>");
?>
</main>
{% endblock %}
