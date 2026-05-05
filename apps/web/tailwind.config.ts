import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        berkeley: {
          blue: "#003262",
          gold: "#FDB515",
        },
      },
    },
  },
  plugins: [],
};

export default config;
