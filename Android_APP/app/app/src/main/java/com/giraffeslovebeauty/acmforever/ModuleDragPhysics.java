package com.giraffeslovebeauty.acmforever;

import java.util.*;

/** Independent row springs and border contacts. Contact propagates from current positions. */
final class ModuleDragPhysics {
    private final float[] height, y, velocity;
    private final ArrayList<Integer> order = new ArrayList<>();
    private final int selected;
    private final float gap, anticipation;
    private float lastTop;
    private int direction;
    ModuleDragPhysics(float[] heights, int selected, float gap, float anticipation) {
        this.height = heights.clone(); this.selected = selected; this.gap = gap; this.anticipation = anticipation;
        y = new float[heights.length]; velocity = new float[heights.length];
        float top = 0;
        for (int i = 0; i < heights.length; i++) { order.add(i); y[i] = top; top += heights[i] + gap; }
        lastTop = y[selected];
    }
    float position(int id) { return y[id]; }
    List<Integer> order() { return new ArrayList<>(order); }
    private float slot(int index) { float top = 0; for (int i = 0; i < index; i++) top += height[order.get(i)] + gap; return top; }
    void step(float requestedTop, float seconds) {
        float dt = Math.max(.001f, Math.min(.032f, seconds));
        float total = slot(order.size() - 1) + height[order.get(order.size() - 1)];
        float top = Math.max(0, Math.min(total - height[selected], requestedTop));
        float delta = top - lastTop;
        if (Math.abs(delta) > .01f) direction = delta > 0 ? 1 : -1;
        float lead = anticipation + Math.min(anticipation * 2, Math.abs(delta) / dt * .025f);
        lastTop = top; y[selected] = top;
        int from = order.indexOf(selected), to = from;
        float center = top + height[selected] / 2;
        while (to > 0 && center < slot(to - 1) + height[order.get(to - 1)] / 2) to--;
        while (to < order.size() - 1 && center > slot(to + 1) + height[order.get(to + 1)] / 2) to++;
        if (to != from) { order.remove(from); order.add(to, selected); }
        float[] target = new float[height.length];
        for (int i = 0; i < order.size(); i++) target[order.get(i)] = slot(i);
        int index = order.indexOf(selected);
        // Visual bounds are the 90% row border, not its centre or the unscaled layout box.
        // Each neighbour reads the preceding row's CURRENT position, so displacement ripples.
        if (direction > 0) for (int i = index + 1; i < order.size(); i++) {
            int current = order.get(i), previous = order.get(i - 1);
            float limit = y[previous] + height[previous] * .95f + gap + (previous == selected ? lead : anticipation) - height[current] * .05f;
            target[current] = Math.max(target[current], limit);
        }
        if (direction < 0) for (int i = index - 1; i >= 0; i--) {
            int current = order.get(i), next = order.get(i + 1);
            float limit = y[next] + height[next] * .05f - gap - (next == selected ? lead : anticipation) - height[current] * .95f;
            target[current] = Math.min(target[current], limit);
        }
        for (int id : order) if (id != selected) {
            velocity[id] = (velocity[id] + (target[id] - y[id]) * 420 * dt) * (float) Math.exp(-26 * dt);
            y[id] += velocity[id] * dt;
            if (Math.abs(target[id] - y[id]) < .05f && Math.abs(velocity[id]) < .2f) { y[id] = target[id]; velocity[id] = 0; }
        }
    }
}
