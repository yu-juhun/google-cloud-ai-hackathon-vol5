// Display offsets only: geographic anchors remain unchanged.
export function spreadMapAgents(agents, positions, width, height) {
  const compact = width <= 700
  const gapX = compact ? 68 : 146, gapY = compact ? 68 : 86
  const paddingX = compact ? 38 : 78, paddingY = 78
  const occupied = [], candidates = []
  const inPanel = p => !compact && ((p.x < 390 && p.y > height - 510) || (p.x > width - 330 && p.y < 400))
  for (let y = paddingY; y <= height - paddingY; y += gapY) {
    for (let x = paddingX; x <= width - paddingX; x += gapX) {
      if (!inPanel({ x, y })) candidates.push({ x, y })
    }
  }
  return agents.map(agent => {
    const anchor = positions?.get(agent.detail.reports[0]?.place_id)
    if (!anchor) return agent
    const origin = { x: anchor.x * width / 100, y: anchor.y * height / 100 }
    const fits = p => p.x >= paddingX && p.x <= width - paddingX && p.y >= paddingY && p.y <= height - paddingY
      && !inPanel(p) && occupied.every(other => Math.abs(p.x - other.x) >= gapX || Math.abs(p.y - other.y) >= gapY)
    const point = [origin, ...candidates].filter(fits).sort((a, b) =>
      (a.x - origin.x) ** 2 + (a.y - origin.y) ** 2 - (b.x - origin.x) ** 2 - (b.y - origin.y) ** 2)[0] || origin
    occupied.push(point)
    return { ...agent, x: point.x / width * 100, y: point.y / height * 100, anchorX: anchor.x, anchorY: anchor.y }
  })
}
