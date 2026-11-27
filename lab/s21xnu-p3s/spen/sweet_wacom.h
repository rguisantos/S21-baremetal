/*
 * sweet_wacom.h: S Pen of the Galaxy S21 Ultra (p3s), Wacom W9020 coordinate packets.
 *
 * Pure functions, no kernel API: the decoder an XNU driver will call on each 16-byte packet read from the
 * digitizer (I2C 0x56, packet id = byte 0 low nibble = 1). Written for S21-baremetal and checked on the host
 * against Samsung's own wacom_i2c_coord_handler() (FlopKernel dc17ad0, drivers/input/sec_input/wacom), which
 * is the behaviour Android shows on this phone:
 *   - byte 0: 0x80 ready (pen in range), 0x40 eraser, 0x20 side button, 0x10 tip contact;
 *   - x, y big endian in bytes 1-4, pressure 12 bits in 5-6, height in 7, tilt x/y signed in 8/9;
 *   - origin, then x/y inversion (negating that tilt), then the x/y swap, all in 16-bit unsigned arithmetic;
 *   - the first ready packet only marks the pen in range (nothing reported); later ones report;
 *   - a ready packet outside the panel after the transform is dropped without changing the state;
 *   - a packet without ready ends the pen (out of range) and clears the state.
 * p3s, DT r19..r22: wacom,invert = <1 0 1> (x inverted, axes swapped); raw maxima from the IC (Android shows
 * ABS_X 0..7099, ABS_Y 0..15776, so max_x = 15776 and max_y = 7099 before the swap).
 */
#ifndef SWEET_WACOM_H
#define SWEET_WACOM_H

#include <stdint.h>

struct sweet_wacom_cfg {
	uint32_t origin_x, origin_y;
	int max_x, max_y;               /* raw, before the swap */
	int x_invert, y_invert, xy_switch;
};

struct sweet_wacom_state {
	int prox, pressed, side;
	uint32_t moves;
};

enum sweet_wacom_kind {
	SWEET_PEN_NONE = 0,             /* not ready and not in range: nothing to do */
	SWEET_PEN_IN_RANGE = 1,         /* first ready packet: the pen came near, nothing reported yet */
	SWEET_PEN_REPORT = 2,           /* position, pressure, height, tilt, buttons */
	SWEET_PEN_OUT = 3,              /* the pen left: release everything */
	SWEET_PEN_DROP = 4,             /* ready packet outside the panel: ignored */
};

struct sweet_wacom_ev {
	int kind;
	uint16_t x, y, pressure, height; /* panel orientation: x 0..max_y, y 0..max_x when swapped */
	int8_t tilt_x, tilt_y;
	int touch, side, eraser;
	int touch_down, touch_up;       /* tip transitions, for the driver's log */
};

static inline int
sweet_wacom_coord(struct sweet_wacom_state *s, const struct sweet_wacom_cfg *c, const uint8_t d[16],
    struct sweet_wacom_ev *e)
{
	uint16_t x = (uint16_t)((d[1] << 8) | d[2]), y = (uint16_t)((d[3] << 8) | d[4]), t;
	int8_t tx = (int8_t)d[8], ty = (int8_t)d[9], tt;
	int bad;

	*e = (struct sweet_wacom_ev){ 0 };
	x = (uint16_t)(x - c->origin_x);
	y = (uint16_t)(y - c->origin_y);
	if (c->x_invert) {
		x = (uint16_t)(c->max_x - x);
		tx = (int8_t)-tx;
	}
	if (c->y_invert) {
		y = (uint16_t)(c->max_y - y);
		ty = (int8_t)-ty;
	}
	if (c->xy_switch) {
		t = x, x = y, y = t;
		tt = tx, tx = ty, ty = tt;
	}
	if (!(d[0] & 0x80)) {
		e->kind = s->prox ? SWEET_PEN_OUT : SWEET_PEN_NONE;
		e->x = x, e->y = y;
		e->touch_up = s->pressed;
		*s = (struct sweet_wacom_state){ 0 };
		return e->kind;
	}
	bad = c->xy_switch ? (x > c->max_y || y > c->max_x) : (x > c->max_x || y > c->max_y);
	if (bad) {
		return e->kind = SWEET_PEN_DROP;
	}
	e->x = x, e->y = y;
	e->pressure = (uint16_t)(((d[5] & 0x0f) << 8) | d[6]);
	e->height = d[7];
	e->tilt_x = tx, e->tilt_y = ty;
	e->touch = !!(d[0] & 0x10);
	e->side = !!(d[0] & 0x20);
	e->eraser = !!(d[0] & 0x40);
	if (!s->prox) {
		s->prox = 1;
		return e->kind = SWEET_PEN_IN_RANGE;
	}
	e->touch_down = e->touch && !s->pressed;
	e->touch_up = !e->touch && s->pressed;
	s->pressed = e->touch;
	s->side = e->side;
	s->moves++;
	return e->kind = SWEET_PEN_REPORT;
}

/* raw panel coordinate (0..max) to pixels (0..px-1), rounding to nearest */
static inline uint32_t
sweet_wacom_to_px(uint32_t v, uint32_t max, uint32_t px)
{
	uint64_t p = ((uint64_t)v * (px - 1) + max / 2) / (max ? max : 1);
	return (uint32_t)(p > px - 1 ? px - 1 : p);
}

#endif
