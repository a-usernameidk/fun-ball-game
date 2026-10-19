import math
import random


def update_ball_physics(
    balls,
    cx,
    cy,
    radius,
    gap_angle,
    gap_width,
    num_gaps,
    dt,
    gravity_wells,
    friction,
    bounciness,
    collision_enabled,
    trails_enabled,
):
  if collision_enabled:
    for i in range(len(balls)):
      for j in range(i + 1, len(balls)):
        b1 = balls[i]
        b2 = balls[j]
        dx = b2["x"] - b1["x"]
        dy = b2["y"] - b1["y"]
        dist = math.sqrt(dx * dx + dy * dy)
        min_dist = b1["radius"] + b2["radius"]
        if dist < min_dist and dist > 0:
          overlap = min_dist - dist
          nx = dx / dist
          ny = dy / dist
          b1["x"] -= nx * overlap * 0.5
          b1["y"] -= ny * overlap * 0.5
          b2["x"] += nx * overlap * 0.5
          b2["y"] += ny * overlap * 0.5
          kx = b1["vx"] - b2["vx"]
          ky = b1["vy"] - b2["vy"]
          p = 2 * (nx * kx + ny * ky) / 2
          b1["vx"] -= p * nx * bounciness
          b1["vy"] -= p * ny * bounciness
          b2["vx"] += p * nx * bounciness
          b2["vy"] += p * ny * bounciness

  new_balls_to_add = 0
  surviving_balls = []
  for b in balls:
    for gw in gravity_wells:
      gdx = gw["x"] - b["x"]
      gdy = gw["y"] - b["y"]
      gdist = math.sqrt(gdx * gdx + gdy * gdy)
      if gdist > 10:
        gforce = gw["strength"] / (gdist * 0.1 + 1)
        direction = -1 if gw.get("type", "attractive") == "repulsive" else 1
        b["vx"] += (gdx / gdist) * gforce * dt * direction
        b["vy"] += (gdy / gdist) * gforce * dt * direction

    b["vx"] *= friction
    b["vy"] *= friction
    b["x"] += b["vx"] * dt
    b["y"] += b["vy"] * dt
    b["vy"] += 0.12 * dt

    if trails_enabled:
      b["history"].append((b["x"], b["y"]))
      if len(b["history"]) > 10:
        b["history"].pop(0)
    else:
      b["history"].clear()

    dx = b["x"] - cx
    dy = b["y"] - cy
    dist = math.sqrt(dx * dx + dy * dy)

    if not b["escaped"]:
      if dist + b["radius"] >= radius:
        theta = math.atan2(-dy, dx)
        if theta < 0:
          theta += 2 * math.pi
        in_any_gap = False
        for g in range(num_gaps):
          g_offset = (gap_angle + g * (2 * math.pi / num_gaps)) % (2 * math.pi)
          norm_gap = (g_offset + 2 * math.pi) % (2 * math.pi)
          gap_end = (norm_gap + gap_width) % (2 * math.pi)
          if norm_gap < gap_end:
            if norm_gap <= theta <= gap_end:
              in_any_gap = True
              break
          else:
            if theta >= norm_gap or theta <= gap_end:
              in_any_gap = True
              break
        if in_any_gap:
          b["escaped"] = True
        else:
          wall_theta = math.atan2(dy, dx)
          b["x"] = cx + (radius - b["radius"]) * math.cos(wall_theta)
          b["y"] = cy + (radius - b["radius"]) * math.sin(wall_theta)
          nx, ny = math.cos(wall_theta), math.sin(wall_theta)
          dot = b["vx"] * nx + b["vy"] * ny
          b["vx"] = (b["vx"] - 2 * dot * nx) * bounciness
          b["vy"] = (b["vy"] - 2 * dot * ny) * bounciness
          b["vx"] *= 1.03
          b["vy"] *= 1.03
    else:
      if dist > radius + 150:
        new_balls_to_add += 2
        continue

    surviving_balls.append(b)

  return surviving_balls, new_balls_to_add