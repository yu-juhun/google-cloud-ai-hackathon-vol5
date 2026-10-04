// Stable identity across the fleet preview, waiting screen, map and reports.
const portraits = ['/images/agent-hinata.png', '/images/agent-moving.png', '/images/agent-exploring.png']
const tones = ['#78add0', '#dfa0b7', '#94bca0', '#b0a2d2', '#d2b080', '#7cbdbb', '#a1b5d5', '#d9a58e', '#adc18d', '#a59fc4']

export const avatarFor = (index = 0, generated) => generated || portraits[index % portraits.length]
export const avatarTone = (index = 0) => tones[index % tones.length]
