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
 *     // POS Settings “Test connection” / key sync (CheckoutPay production):
 *     Route::post('/terminals/sync-signing-key', [BroadcastVerifyController::class, 'syncSigningKey']);
 * });
 *
 * Copy deploy/laravel/config-broadcast.php to config/broadcast.php in the Laravel app.
 * Copy BroadcastVerifyController.php into App\Http\Controllers\Api (Cheko-proven open-until-paid + wire expand).
 */
