package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import android.graphics.*;
import android.view.View;

/** Existing approved character layers with two original tear shapes; follows the chosen theme. */
final class CryingCatView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
    private final RectF bounds = new RectF(0, 0, 512, 512);
    private final Path tears = new Path();
    private final Bitmap character;
    CryingCatView(Context context) {
        super(context); setContentDescription("哭泣的猫娘"); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        character = CharacterArt.bitmap(context, R.drawable.avatar_catgirl);
        for (int x : new int[]{177, 291}) {
            float y = x == 177 ? 382 : 400;
            tears.moveTo(x, y); tears.cubicTo(x - 2, y + 14, x - 21, y + 32, x - 17, y + 45);
            tears.cubicTo(x - 10, y + 65, x + 13, y + 55, x + 11, y + 42);
            tears.cubicTo(x + 10, y + 27, x + 3, y + 12, x, y); tears.close();
        }
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas); float side = Math.min(getWidth(), getHeight()); int save = canvas.save();
        canvas.translate((getWidth() - side) / 2, (getHeight() - side) / 2); canvas.scale(side / 512, side / 512);
        paint.setColor(Color.WHITE); canvas.drawBitmap(character, null, bounds, paint);
        paint.setColor(0xdd79c9e9); canvas.drawPath(tears, paint);
        canvas.restoreToCount(save);
    }
}
