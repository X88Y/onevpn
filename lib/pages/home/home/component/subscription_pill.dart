import 'package:flutter/material.dart';
import 'package:mvmvpn/core/db/database/constants.dart';
import 'package:mvmvpn/l10n/localizations/app_localizations.dart';
import 'package:mvmvpn/service/event_bus/state.dart';

class SubscriptionPill extends StatelessWidget {
  final AppEventBusState eventState;
  final AnimationController shimmerController;

  const SubscriptionPill({
    super.key,
    required this.eventState,
    required this.shimmerController,
  });

  @override
  Widget build(BuildContext context) {
    final isRunning = eventState.runningId != DBConstants.defaultId;
    final user = eventState.userData;
    final hasActiveSubscription = user?.hasActiveSubscription ?? false;
    final subscriptionEndsAt = user?.subscriptionEndsAt;

    if (isRunning || hasActiveSubscription) {
      final statusText = subscriptionEndsAt != null
          ? AppLocalizations.of(context)!.mainSubscriptionActiveUntil(
              '${subscriptionEndsAt.day.toString().padLeft(2, '0')}.${subscriptionEndsAt.month.toString().padLeft(2, '0')}.${subscriptionEndsAt.year}')
          : AppLocalizations.of(context)!.mainSubscriptionActive;
          
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: LinearGradient(
            colors: [
              Colors.green.withOpacity(0.15),
              Colors.teal.withOpacity(0.1),
            ],
          ),
          border: Border.all(color: Colors.green.withOpacity(0.3)),
          boxShadow: [
            BoxShadow(
              color: Colors.green.withOpacity(0.15),
              blurRadius: 16,
            )
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(18),
          child: Stack(
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.verified_rounded, color: Colors.green, size: 18),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(
                      statusText,
                      style: const TextStyle(
                        color: Colors.green,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                      overflow: TextOverflow.visible,
                    ),
                  ),
                ],
              ),
              // Shimmer overlay
              Positioned.fill(
                child: AnimatedBuilder(
                  animation: shimmerController,
                  builder: (context, child) {
                    return FractionallySizedBox(
                      widthFactor: 0.3,
                      alignment: Alignment(-1.5 + (shimmerController.value * 3), 0),
                      child: Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              Colors.white.withOpacity(0),
                              Colors.white.withOpacity(0.2),
                              Colors.white.withOpacity(0),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        color: Colors.white.withOpacity(0.04),
        border: Border.all(color: Colors.white.withOpacity(0.07)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.lock_outline_rounded, color: Colors.white.withOpacity(0.35), size: 18),
          const SizedBox(width: 10),
          Text(
            AppLocalizations.of(context)!.mainNoActiveSubscription,
            style: TextStyle(
              color: Colors.white.withOpacity(0.35),
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
