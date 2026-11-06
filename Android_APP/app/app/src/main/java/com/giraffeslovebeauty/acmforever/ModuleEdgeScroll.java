package com.giraffeslovebeauty.acmforever;

/** Time-based edge scrolling, with fractional pixels and a gentle speed ramp. */
final class ModuleEdgeScroll {
    private static final float MAX_DP_PER_SECOND = 96, RAMP_SECONDS = .12f;
    private final float density;
    private float speed, fraction;
    ModuleEdgeScroll(float density) { this.density = density; }
    void reset() { speed = 0; fraction = 0; }
    int step(float pointerY, float viewportHeight, float edgeSize, float seconds) {
        if (viewportHeight <= 0 || edgeSize <= 0 || density <= 0 || seconds <= 0) { reset(); return 0; }
        float zone = Math.min(edgeSize, viewportHeight / 3);
        float depth = pointerY < zone ? (pointerY - zone) / zone
                : pointerY > viewportHeight - zone ? (pointerY - viewportHeight + zone) / zone : 0;
        depth = Math.max(-1, Math.min(1, depth));
        if (depth == 0) { reset(); return 0; }
        float target = MAX_DP_PER_SECOND * density * depth * Math.abs(depth);
        if (speed * target < 0) reset();
        float dt = Math.min(.05f, seconds), decay = (float) Math.exp(-dt / RAMP_SECONDS);
        // Integrate the ramp so 60Hz and 120Hz travel the same distance.
        fraction += target * dt + (speed - target) * RAMP_SECONDS * (1 - decay);
        speed = target + (speed - target) * decay;
        int delta = (int) fraction;
        fraction -= delta;
        return delta;
    }
}
