package de.wissensfreund.wissensfreund_app

import android.app.Activity
import android.content.Context
import android.os.Handler
import android.os.Looper
import com.android.billingclient.api.*
import io.flutter.plugin.common.MethodChannel
import kotlinx.coroutines.*

class BillingService(
    private val context: Context,
    private val getActivity: () -> Activity?
) : PurchasesUpdatedListener {

    companion object {
        const val PRODUCT_PLUS    = "wissensfreund_plus"
        const val PRODUCT_PREMIUM = "wissensfreund_premium"
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pendingResult: MethodChannel.Result? = null

    private val billingClient: BillingClient = BillingClient.newBuilder(context)
        .setListener(this)
        .enablePendingPurchases()
        .build()

    // ── Connection ──────────────────────────────────────────────────────────────

    private fun ensureConnected(onReady: () -> Unit) {
        if (billingClient.isReady) { onReady(); return }
        billingClient.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(r: BillingResult) {
                if (r.responseCode == BillingClient.BillingResponseCode.OK) onReady()
            }
            override fun onBillingServiceDisconnected() { /* retry on next call */ }
        })
    }

    // ── Public API (called from MethodChannel) ──────────────────────────────────

    fun getStatus(result: MethodChannel.Result) {
        ensureConnected {
            scope.launch {
                val tier = resolveTier()
                withContext(Dispatchers.Main) { result.success(tier) }
            }
        }
    }

    fun purchasePlus(result: MethodChannel.Result) {
        pendingResult = result
        launchFlow(PRODUCT_PLUS, BillingClient.ProductType.INAPP)
    }

    fun subscribePremium(result: MethodChannel.Result) {
        pendingResult = result
        launchFlow(PRODUCT_PREMIUM, BillingClient.ProductType.SUBS)
    }

    fun restorePurchases(result: MethodChannel.Result) {
        ensureConnected {
            scope.launch {
                val tier = resolveTier()
                withContext(Dispatchers.Main) { result.success(tier) }
            }
        }
    }

    fun destroy() {
        scope.cancel()
        billingClient.endConnection()
    }

    // ── Tier resolution ─────────────────────────────────────────────────────────

    private suspend fun resolveTier(): String {
        // Check subscription (Premium) first.
        val subResult = billingClient.queryPurchasesAsync(
            QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.SUBS).build()
        )
        for (p in subResult.purchasesList) {
            if (p.products.contains(PRODUCT_PREMIUM) &&
                p.purchaseState == Purchase.PurchaseState.PURCHASED) {
                acknowledgeIfNeeded(p)
                return "premium"
            }
        }
        // Check one-time purchase (Plus).
        val inappResult = billingClient.queryPurchasesAsync(
            QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.INAPP).build()
        )
        for (p in inappResult.purchasesList) {
            if (p.products.contains(PRODUCT_PLUS) &&
                p.purchaseState == Purchase.PurchaseState.PURCHASED) {
                acknowledgePurchaseIfNeeded(p)
                return "plus"
            }
        }
        return "free"
    }

    private fun acknowledgeIfNeeded(purchase: Purchase) = acknowledgePurchaseIfNeeded(purchase)

    private fun acknowledgePurchaseIfNeeded(purchase: Purchase) {
        if (purchase.isAcknowledged) return
        scope.launch {
            billingClient.acknowledgePurchase(
                AcknowledgePurchaseParams.newBuilder()
                    .setPurchaseToken(purchase.purchaseToken).build()
            )
        }
    }

    // ── Purchase flow ───────────────────────────────────────────────────────────

    private fun launchFlow(productId: String, productType: String) {
        val activity = getActivity()
        if (activity == null) {
            pendingResult?.error("NO_ACTIVITY", "No activity", null)
            pendingResult = null
            return
        }
        ensureConnected {
            val params = QueryProductDetailsParams.newBuilder()
                .setProductList(listOf(
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(productId)
                        .setProductType(productType).build()
                )).build()

            // callback-based API (no -ktx required)
            billingClient.queryProductDetailsAsync(params) { billingResult, detailsList ->
                if (billingResult.responseCode != BillingClient.BillingResponseCode.OK
                    || detailsList.isEmpty()) {
                    Handler(Looper.getMainLooper()).post {
                        pendingResult?.error("NOT_FOUND", "Product $productId not found", null)
                        pendingResult = null
                    }
                    return@queryProductDetailsAsync
                }
                val details = detailsList.first()
                val paramsBuilder = BillingFlowParams.ProductDetailsParams.newBuilder()
                    .setProductDetails(details)
                if (productType == BillingClient.ProductType.SUBS) {
                    val offerToken = details.subscriptionOfferDetails?.firstOrNull()?.offerToken
                    if (offerToken != null) paramsBuilder.setOfferToken(offerToken)
                }
                val productParams = paramsBuilder.build()
                val flowParams = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(listOf(productParams)).build()

                Handler(Looper.getMainLooper()).post {
                    billingClient.launchBillingFlow(activity, flowParams)
                }
            }
        }
    }

    // ── PurchasesUpdatedListener ────────────────────────────────────────────────

    override fun onPurchasesUpdated(billingResult: BillingResult, purchases: List<Purchase>?) {
        when (billingResult.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                purchases?.forEach { p ->
                    if (p.purchaseState == Purchase.PurchaseState.PURCHASED) {
                        acknowledgePurchaseIfNeeded(p)
                    }
                }
                scope.launch {
                    val tier = resolveTier()
                    withContext(Dispatchers.Main) {
                        pendingResult?.success(tier)
                        pendingResult = null
                    }
                }
            }
            BillingClient.BillingResponseCode.USER_CANCELED -> {
                pendingResult?.success("cancelled")
                pendingResult = null
            }
            else -> {
                pendingResult?.error("BILLING_ERROR", billingResult.debugMessage,
                    billingResult.responseCode)
                pendingResult = null
            }
        }
    }
}
