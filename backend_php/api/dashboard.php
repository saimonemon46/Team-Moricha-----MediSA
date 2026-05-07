<?php
// MediAI — API: Dashboard Stats
require_once '../includes/config.php';

header('Access-Control-Allow-Origin: *');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { exit(0); }

$user_id = (int)($_GET['user_id'] ?? 0);
if (!$user_id) { jsonResponse(['success'=>false,'message'=>'user_id required']); }

$db = getDB();

$sessions   = $db->prepare('SELECT COUNT(*) FROM symptom_sessions WHERE user_id=?');
$sessions->execute([$user_id]); $sc = (int)$sessions->fetchColumn();

$reports    = $db->prepare('SELECT COUNT(*) FROM triage_reports WHERE user_id=? AND created_at >= DATE_FORMAT(NOW(),"%%Y-%%m-01")');
$reports->execute([$user_id]); $rc = (int)$reports->fetchColumn();

$meds       = $db->prepare('SELECT COUNT(*) FROM medication_schedule WHERE user_id=? AND active=1');
$meds->execute([$user_id]); $mc = (int)$meds->fetchColumn();

$appts      = $db->prepare('SELECT COUNT(*) FROM appointments WHERE user_id=? AND appointment_date >= NOW() AND status != "cancelled"');
$appts->execute([$user_id]); $ac = (int)$appts->fetchColumn();

$recentStmt = $db->prepare('SELECT possible_condition, urgency, created_at FROM triage_reports WHERE user_id=? ORDER BY created_at DESC LIMIT 5');
$recentStmt->execute([$user_id]);
$recentReports = $recentStmt->fetchAll();

jsonResponse([
    'success'        => true,
    'sessions'       => $sc,
    'reports'        => $rc,
    'medications'    => $mc,
    'appointments'   => $ac,
    'recent_reports' => $recentReports
]);
