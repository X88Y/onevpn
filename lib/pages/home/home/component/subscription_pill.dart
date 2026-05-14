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
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(
            colors: [
              const Color(0xFF00E5A0).withOpacity(0.12),
              const Color(0xFF00B8D4).withOpacity(0.08),
            ],
          ),
          border: Border.all(color: const Color(0xFF00E5A0).withOpacity(0.25)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF00E5A0).withOpacity(0.1),
              blurRadius: 20,
              spreadRadius: 2,
            )
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: Stack(
            children: [
              Row(
                children: [
                  _buildSignalBars(),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'SYSTEM ONLINE',
                          style: TextStyle(
                            color: const Color(0xFF00E5A0).withOpacity(0.6),
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.5,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          statusText,
                          style: const TextStyle(
                            color: Color(0xFF00E5A0),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                  _buildBlinkingDot(),
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
                              Colors.white.withOpacity(0.15),
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
        borderRadius: BorderRadius.circular(16),
        color: Colors.white.withOpacity(0.03),
        border: Border.all(color: Colors.white.withOpacity(0.06)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.lock_outline_rounded, color: Colors.white.withOpacity(0.3), size: 16),
          const SizedBox(width: 10),
          Text(
            AppLocalizations.of(context)!.mainNoActiveSubscription,
            style: TextStyle(
              color: Colors.white.withOpacity(0.35),
              fontSize: 13,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSignalBars() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Container(
          width: 3,
          height: 6,
          decoration: BoxDecoration(
            color: const Color(0xFF00E5A0).withOpacity(0.4),
            borderRadius: BorderRadius.circular(1),
          ),
        ),
        const SizedBox(width: 2),
        Container(
          width: 3,
          height: 10,
          decoration: BoxDecoration(
            color: const Color(0xFF00E5A0).withOpacity(0.6),
            borderRadius: BorderRadius.circular(1),
          ),
        ),
        const SizedBox(width: 2),
        Container(
          width: 3,
          height: 14,
          decoration: BoxDecoration(
            color: const Color(0xFF00E5A0),
            borderRadius: BorderRadius.circular(1),
          ),
        ),
      ],
    );
  }

  Widget _buildBlinkingDot() {
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: const Color(0xFF00E5A0),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF00E5A0).withOpacity(0.6),
            blurRadius: 8,
            spreadRadius: 2,
          ),
        ],
      ),
    );
  }
}
