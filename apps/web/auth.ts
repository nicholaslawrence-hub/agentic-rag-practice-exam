import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import ResendProvider from "next-auth/providers/resend";

export const { handlers, auth, signIn, signOut } = NextAuth({
  secret: process.env.NEXTAUTH_SECRET,
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          // Restrict to Berkeley Google accounts
          hd: "berkeley.edu",
        },
      },
    }),
    ResendProvider({
      apiKey: process.env.RESEND_API_KEY!,
      from: "MCB Tutor <noreply@mcbtutor.berkeley.edu>",
    }),
  ],
  callbacks: {
    async signIn({ account, profile }) {
      // Extra guard: verify the email domain regardless of provider
      const email = (profile as any)?.email as string | undefined;
      if (!email) return false;
      if (!email.endsWith("@berkeley.edu")) return false;
      return true;
    },
    async jwt({ token, account }) {
      return token;
    },
    async session({ session, token }) {
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
});
