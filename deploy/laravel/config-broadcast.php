<?php

return [
    'admin_key' => env('BROADCAST_ADMIN_KEY'),
    'rate_limit_verify' => (int) env('BROADCAST_RATE_LIMIT_VERIFY', 120),
];
