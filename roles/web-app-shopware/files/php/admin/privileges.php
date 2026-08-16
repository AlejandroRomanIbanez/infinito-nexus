<?php
/**
 * Required env:
 *   DATABASE_URL  connection string of the Shopware database
 *   ADMIN_USER    username whose admin flag is enforced
 */

declare(strict_types=1);

$url = parse_url(getenv('DATABASE_URL') ?: '');
$dsn = sprintf(
    'mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
    $url['host'] ?? 'localhost',
    $url['port'] ?? 3306,
    ltrim($url['path'] ?? '', '/')
);

$pdo = new PDO($dsn, $url['user'] ?? '', $url['pass'] ?? '', [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$statement = $pdo->prepare('UPDATE `user` SET admin = 1 WHERE username = ?');
$statement->execute([getenv('ADMIN_USER')]);

printf("admin flag asserted for %s (%d row(s))\n", getenv('ADMIN_USER'), $statement->rowCount());
