export const examples = [
  {
    id: "average",
    label: "Python · Empty-input bug",
    title: "Example · Average calculation",
    language: "python",
    code: "def average(values):\n    return sum(values) / len(values)\n",
  },
  {
    id: "async",
    label: "TypeScript · Async iteration",
    title: "Example · Saving items",
    language: "typescript",
    code: "async function saveAll(items: string[], save: (x: string) => Promise<void>) {\n  items.forEach(async (item) => {\n    await save(item);\n  });\n}\n",
  },
  {
    id: "safe",
    label: "Python · Guarded average",
    title: "Example · Guarded average",
    language: "python",
    code: 'def average(values):\n    if not values:\n        raise ValueError("No values")\n    return sum(values) / len(values)\n',
  },
];
