/**
 * OptiWays Firebase Cloud Functions
 * Node 22 compatible — all free tier
 */

const functions = require("firebase-functions/v1");
const { onSchedule } = require("firebase-functions/v2/scheduler");
const { setGlobalOptions } = require("firebase-functions/v2");
const admin = require("firebase-admin");

admin.initializeApp();
const db = admin.firestore();

setGlobalOptions({ region: "asia-east1" });

// ─────────────────────────────────────────────────────────────────────────────
// REPORT MODERATION — v1 Firestore trigger (no Eventarc needed)
// Verifies report when >= 2 upvotes OR reporter trustScore >= 0.7
// ─────────────────────────────────────────────────────────────────────────────
exports.moderateReport = functions
  .region("asia-east1")
  .firestore.document("incident_reports/{reportId}")
  .onUpdate(async (change, context) => {
    const before = change.before.data();
    const after = change.after.data();

    if (before.upvotes === after.upvotes) return null;
    if (after.status !== "PENDING") return null;

    const shouldVerify =
      after.upvotes >= 2 ||
      after.reporterTrustScore >= 0.7;

    if (!shouldVerify) return null;

    await change.after.ref.update({ status: "VERIFIED" });

    const reporterRef = db.collection("user_profiles").doc(after.reporterId);
    await db.runTransaction(async (transaction) => {
      const profileDoc = await transaction.get(reporterRef);
      if (!profileDoc.exists) return;

      const profile = profileDoc.data();
      const newVerified = (profile.verifiedReports || 0) + 1;
      const newTotal = Math.max(profile.totalReports || 1, 1);
      const newTrust = Math.min(newVerified / newTotal, 1.0);

      transaction.update(reporterRef, {
        points: admin.firestore.FieldValue.increment(50),
        verifiedReports: newVerified,
        trustScore: newTrust,
      });
    });

    console.log(`✅ Report ${context.params.reportId} verified.`);
    return null;
  });

// ─────────────────────────────────────────────────────────────────────────────
// NEW USER — Create Firestore profile when user registers
// Uses v1 auth trigger — free, no GCIP needed
// ─────────────────────────────────────────────────────────────────────────────
exports.onUserCreated = functions
  .region("asia-east1")
  .auth.user()
  .onCreate(async (user) => {
    const profileRef = db.collection("user_profiles").doc(user.uid);
    const existing = await profileRef.get();

    if (!existing.exists) {
      await profileRef.set({
        uid: user.uid,
        displayName: user.displayName || "Anonymous",
        email: user.email || "",
        photoUrl: user.photoURL || "",
        preferredProfile: "default",
        isStudent: false,
        isPwd: false,
        points: 0,
        trustScore: 0.0,
        verifiedReports: 0,
        totalReports: 0,
        helpfulVotes: 0,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        lastActiveAt: admin.firestore.FieldValue.serverTimestamp(),
      });
      console.log(`👤 Profile created for ${user.uid}`);
    }
    return null;
  });

// ─────────────────────────────────────────────────────────────────────────────
// AUTO-EXPIRE reports after 2 hours — runs every 30 minutes
// ─────────────────────────────────────────────────────────────────────────────
exports.expireOldReports = onSchedule(
  { schedule: "every 30 minutes", region: "asia-east1" },
  async () => {
    const now = admin.firestore.Timestamp.now();
    const expiredReports = await db
      .collection("incident_reports")
      .where("expiresAt", "<=", now)
      .where("isActive", "==", true)
      .get();

    if (expiredReports.empty) {
      console.log("No reports to expire.");
      return null;
    }

    const batch = db.batch();
    expiredReports.forEach((doc) => {
      batch.update(doc.ref, { status: "EXPIRED", isActive: false });
    });

    await batch.commit();
    console.log(`⏰ Expired ${expiredReports.size} reports.`);
    return null;
  }
);