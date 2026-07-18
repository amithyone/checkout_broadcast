<?php

/**
 * Add to routes/api.php in checkout Laravel app (prefix api/v1):
 *
 * use App\Http\Controllers\Api\BroadcastVerifyController;
 *
 * Route::prefix('broadcast')->group(function () {
 *     Route::get('/health', [BroadcastVerifyController::class, 'health']);
 *     Route::post('/verify-broadcast', [BroadcastVerifyController::class, 'verifyBroadcast']);
 *     Route::post('/terminals/register', [BroadcastVerifyController::class, 'registerTerminal']);
 * });
 *
 * Copy deploy/laravel/config-broadcast.php to config/broadcast.php in the Laravel app.
 */
