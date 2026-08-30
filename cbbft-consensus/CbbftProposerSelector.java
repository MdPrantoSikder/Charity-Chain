/*
 * Copyright contributors to Besu.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License. You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed under the License
 * is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
 * or implied. See the License for the specific language governing permissions and limitations under
 * the License.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
package org.hyperledger.besu.consensus.cbbft;

import org.hyperledger.besu.consensus.common.BlockInterface;
import org.hyperledger.besu.consensus.common.bft.ConsensusRoundIdentifier;
import org.hyperledger.besu.consensus.common.bft.blockcreation.BftProposerSelector;
import org.hyperledger.besu.consensus.common.bft.blockcreation.ProposerSelector;
import org.hyperledger.besu.consensus.common.validator.ValidatorProvider;
import org.hyperledger.besu.datatypes.Address;
import org.hyperledger.besu.consensus.common.bft.BftBlockHashing;
import org.hyperledger.besu.consensus.common.bft.BftExtraData;
import org.hyperledger.besu.consensus.common.bft.BftExtraDataCodec;
import org.hyperledger.besu.ethereum.chain.Blockchain;
import org.hyperledger.besu.ethereum.core.BlockHeader;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * CB-BFT proposer selection.
 *
 * <p>Stage 3: delegates entirely to {@link BftProposerSelector}, so behaviour is identical to QBFT.
 * This exists to prove the wiring in isolation. CRITIC scoring, adaptive clustering and pool
 * selection arrive in Stage 5, and must derive every input from block headers only - anything
 * observed locally will differ between nodes and the chain will fork.
 */
public class CbbftProposerSelector implements ProposerSelector {

  private static final Logger LOG = LoggerFactory.getLogger(CbbftProposerSelector.class);

  /**
   * Blocks of chain history each node walks. Thirty blocks is roughly three proposal opportunities
   * per validator at n=10, which bounds adaptation latency to about one minute at a two second
   * block period while leaving enough samples for CRITIC to discriminate.
   */
  private static final int WINDOW = 30;

  private final ProposerSelector delegate;
  private final Blockchain blockchain;
  private final BlockInterface blockInterface;
  private final ValidatorProvider validatorProvider;
  private final BftExtraDataCodec extraDataCodec;
  private final BftBlockHashing blockHashing;

  /**
   * Construct a CB-BFT proposer selector.
   *
   * @param blockchain the blockchain, source of all header-derived attributes
   * @param blockInterface used to recover the proposer of any prior block
   * @param changeEachBlock whether the proposer rotates on every block
   * @param validatorProvider the current validator set
   */
  public CbbftProposerSelector(
      final Blockchain blockchain,
      final BlockInterface blockInterface,
      final boolean changeEachBlock,
      final ValidatorProvider validatorProvider,
      final BftExtraDataCodec extraDataCodec) {
    this.delegate =
        new BftProposerSelector(blockchain, blockInterface, changeEachBlock, validatorProvider);
    this.blockchain = blockchain;
    this.blockInterface = blockInterface;
    this.validatorProvider = validatorProvider;
    this.extraDataCodec = extraDataCodec;
    this.blockHashing = new BftBlockHashing(extraDataCodec);
  }

  private static final class Attr {
    long proposed;
    long seals;
    long gasWadSum;
    long latencySecSum;
    long latencySamples;
  }

  /**
   * Walk the last WINDOW headers below upToBlock and derive the four CRITIC criteria for every
   * current validator. Header data only, so every node computes an identical map.
   *
   * @param upToBlock exclusive upper bound, the sequence being decided
   * @return validator address to raw attributes
   */
  private Map<Address, Attr> collectAttributes(final long upToBlock) {
    final Map<Address, Attr> out = new LinkedHashMap<>();
    final List<Address> validators = new ArrayList<>(validatorProvider.getValidatorsAtHead());
    Collections.sort(validators);
    for (final Address v : validators) {
      out.put(v, new Attr());
    }

    final long to = upToBlock - SCORING_LAG;
    final long from = Math.max(1L, to - WINDOW);
    if (to - from < 3) {
      return null;
    }
    for (long n = from; n < to; n++) {
      final Optional<BlockHeader> maybe = blockchain.getBlockHeader(n);
      if (maybe.isEmpty()) {
        // Incomplete view of the window - refuse to score rather than score on partial data.
        return null;
      }
      final BlockHeader h = maybe.get();

      BftExtraData extra = null;
      try {
        extra = extraDataCodec.decode(h);
      } catch (final RuntimeException e) {
        LOG.debug("CBBFT: could not decode extra data for block {}", n, e);
      }
      final boolean round0Only = extra != null && extra.getRound() == 0;

      final Address proposer = blockInterface.getProposerOfBlock(h);
      final Attr pa = out.get(proposer);
      if (pa != null) {
        pa.proposed++;
        if (h.getGasLimit() > 0) {
          pa.gasWadSum += wdiv(h.getGasUsed(), h.getGasLimit());
        }
        if (n > 1 && round0Only) {
          blockchain
              .getBlockHeader(h.getParentHash())
              .ifPresent(
                  parent -> {
                    pa.latencySecSum += h.getTimestamp() - parent.getTimestamp();
                    pa.latencySamples++;
                  });
        }
      }

      if (extra != null) {
        try {
          final List<Address> committers = blockHashing.recoverCommitterAddresses(h, extra);
          for (final Address c : committers) {
            final Attr ca = out.get(c);
            if (ca != null) {
              ca.seals++;
            }
          }
        } catch (final RuntimeException e) {
          LOG.debug("CBBFT: could not recover seals for block {}", n, e);
        }
      }
    }
    return out;
  }

  /**
   * A validator and its F-score. Ordering is F descending, then address ascending - the address
   * tiebreak is what keeps every node in agreement when scores collide, which they do often at
   * four decimal places.
   */
  private static final class Scored implements Comparable<Scored> {
    final Address id;
    final long f;

    Scored(final Address id, final long f) {
      this.id = id;
      this.f = f;
    }

    @Override
    public int compareTo(final Scored o) {
      final int byScore = Long.compare(o.f, this.f);
      return byScore != 0 ? byScore : this.id.compareTo(o.id);
    }
  }

  /**
   * Fixed-point scale. Every score is held as an integer multiple of 1e-18, so arithmetic is
   * bit-identical on every node. Double arithmetic is not: accumulation order and JIT state change
   * the last bits, which was enough to make validators disagree on the proposer.
   */
  private static final long WAD = 1_000_000_000_000_000_000L;

  /** WAD as a BigInteger, for square roots whose intermediates exceed 64 bits. */
  private static final BigInteger BIG_WAD = BigInteger.valueOf(WAD);

  /** Multiply two WAD values, removing the extra scale factor. */
  private static long wmul(final long a, final long b) {
    // a*b reaches 1e36 when both operands approach WAD, which overflows a 64 bit long. Solidity
    // gets away with the naive form because uint256 has the range; Java does not, so the product
    // is carried as a 128 bit intermediate and divided down.
    final boolean negative = (a < 0) ^ (b < 0);
    final long ua = Math.abs(a);
    final long ub = Math.abs(b);
    final long hi = Math.multiplyHigh(ua, ub);
    final long lo = ua * ub;
    final long q = divide128(hi, lo, WAD);
    return negative ? -q : q;
  }

  /** Divide an unsigned 128 bit value, given as high and low words, by a positive divisor. */
  private static long divide128(final long hi, final long lo, final long div) {
    if (hi == 0) {
      return Long.divideUnsigned(lo, div);
    }
    // Long division over 128 bits, one bit at a time. Values here are bounded well below 2^127,
    // so the shift never loses information.
    long remainder = 0;
    long quotient = 0;
    for (int i = 127; i >= 0; i--) {
      remainder <<= 1;
      final long bit = i >= 64 ? (hi >>> (i - 64)) & 1L : (lo >>> i) & 1L;
      remainder |= bit;
      if (Long.compareUnsigned(remainder, div) >= 0) {
        remainder -= div;
        if (i < 64) {
          quotient |= 1L << i;
        }
      }
    }
    return quotient;
  }

  /** Divide two WAD values, restoring the scale factor lost to division. */
  private static long wdiv(final long a, final long b) {
    if (b == 0) {
      return 0;
    }
    final boolean negative = (a < 0) ^ (b < 0);
    final long ua = Math.abs(a);
    final long ub = Math.abs(b);
    final long hi = Math.multiplyHigh(ua, WAD);
    final long lo = ua * WAD;
    final long q = divide128(hi, lo, ub);
    return negative ? -q : q;
  }

  /**
   * Square root of a WAD value, result WAD scaled. sqrt(x/WAD)*WAD == sqrt(x*WAD), and x*WAD
   * exceeds 64 bits, so the intermediate is carried in BigInteger. Called a few times per scoring
   * pass, so allocation cost is irrelevant next to being provably correct.
   */
  private static long wsqrt(final long x) {
    if (x <= 0) {
      return 0;
    }
    return BigInteger.valueOf(x).multiply(BIG_WAD).sqrt().longValueExact();
  }

  /** Min-max normalise a column into [0, WAD]. Constant column becomes WAD, never inverted. */
  private static long[] normaliseWad(final long[] col, final boolean isCost) {
    final int n = col.length;
    final long[] out = new long[n];
    long lo = col[0];
    long hi = col[0];
    for (int i = 1; i < n; i++) {
      lo = Math.min(lo, col[i]);
      hi = Math.max(hi, col[i]);
    }
    final long range = hi - lo;
    if (range == 0) {
      for (int i = 0; i < n; i++) {
        out[i] = WAD;
      }
      return out;
    }
    for (int i = 0; i < n; i++) {
      out[i] = isCost ? wdiv(hi - col[i], range) : wdiv(col[i] - lo, range);
    }
    return out;
  }

  /** Population standard deviation over WAD values, ddof = 0. */
  private static long stdevWad(final long[] v) {
    final int n = v.length;
    if (n < 2) {
      return 0;
    }
    long sum = 0;
    for (final long x : v) {
      sum += x;
    }
    final long mean = sum / n;
    long acc = 0;
    for (final long x : v) {
      final long d = x - mean;
      acc += wmul(d, d);
    }
    return wsqrt(acc / n);
  }

  /** Pearson correlation over WAD values, clamped to [-WAD, WAD]. */
  private static long pearsonWad(final long[] a, final long[] b) {
    final int n = a.length;
    if (n < 2) {
      return 0;
    }
    long sa = 0;
    long sb = 0;
    for (int i = 0; i < n; i++) {
      sa += a[i];
      sb += b[i];
    }
    final long ma = sa / n;
    final long mb = sb / n;
    long cov = 0;
    long va = 0;
    long vb = 0;
    for (int i = 0; i < n; i++) {
      final long da = a[i] - ma;
      final long db = b[i] - mb;
      cov += wmul(da, db);
      va += wmul(da, da);
      vb += wmul(db, db);
    }
    if (va == 0 || vb == 0) {
      return 0;
    }
    final long denom = wmul(wsqrt(va), wsqrt(vb));
    if (denom == 0) {
      return 0;
    }
    final long r = wdiv(cov, denom);
    return Math.max(-WAD, Math.min(WAD, r));
  }

  /** CRITIC weights over WAD values, summing to WAD. */
  private static long[] criticWeightsWad(final long[][] norm) {
    final int n = norm.length;
    final long[][] cols = new long[CRITERIA][n];
    final long[] sigma = new long[CRITERIA];
    for (int j = 0; j < CRITERIA; j++) {
      for (int i = 0; i < n; i++) {
        cols[j][i] = norm[i][j];
      }
      sigma[j] = stdevWad(cols[j]);
    }

    final long[] c = new long[CRITERIA];
    long total = 0;
    for (int j = 0; j < CRITERIA; j++) {
      long conflict = 0;
      for (int k = 0; k < CRITERIA; k++) {
        if (j == k) {
          continue;
        }
        final long r = (sigma[j] == 0 || sigma[k] == 0) ? 0 : pearsonWad(cols[j], cols[k]);
        conflict += WAD - r;
      }
      c[j] = wmul(sigma[j], conflict);
      total += c[j];
    }

    final long[] w = new long[CRITERIA];
    for (int j = 0; j < CRITERIA; j++) {
      w[j] = total > 0 ? wdiv(c[j], total) : WAD / CRITERIA;
    }
    return w;
  }

  /** Number of CRITIC criteria: cpu, latency, reputation, throughput. */
  /**
   * Blocks excluded at the top of the window. Scoring must never read a block that some peers may
   * not have imported yet, or nodes compute different attributes and elect different proposers.
   */
  private static final int SCORING_LAG = 2;

  /**
   * Three CRITIC criteria: cpu, latency, reputation. Seal participation was removed - QBFT excludes
   * committed seals from the block hash, so nodes legitimately hold the same block with different
   * seal sets and any score derived from them diverges.
   */
  private static final int CRITERIA = 3;

  /** Index of the latency criterion, the only cost-type criterion. */
  private static final int LATENCY = 1;





  /**
   * Derive F-scores for every validator from the attribute window. Deterministic: identical chain
   * state produces an identical, identically ordered list on every node.
   *
   * @param upToBlock the sequence being decided
   * @return validators sorted by F descending, address ascending on ties
   */
  private List<Scored> computeScores(final long upToBlock) {
    final Map<Address, Attr> attrs = collectAttributes(upToBlock);
    final List<Scored> out = new ArrayList<>();
    if (attrs == null) {
      return out;
    }
    final int n = attrs.size();
    if (n == 0) {
      return out;
    }
    final long window = Math.min(WINDOW, Math.max(0L, upToBlock - SCORING_LAG - 1));

    long worstLatencyWad = 0L;
    for (final Attr a : attrs.values()) {
      if (a.latencySamples > 0) {
        worstLatencyWad = Math.max(worstLatencyWad, (a.latencySecSum * WAD) / a.latencySamples);
      }
    }

    final Address[] ids = new Address[n];
    final long[][] rawWad = new long[n][CRITERIA];
    int i = 0;
    for (final Map.Entry<Address, Attr> e : attrs.entrySet()) {
      final Attr a = e.getValue();
      ids[i] = e.getKey();
      rawWad[i][0] = a.proposed > 0 ? a.gasWadSum / a.proposed : 0L;
      rawWad[i][LATENCY] =
          a.latencySamples > 0 ? (a.latencySecSum * WAD) / a.latencySamples : worstLatencyWad;
      rawWad[i][2] = a.proposed * WAD;
      i++;
    }

    if (n < 2) {
      out.add(new Scored(ids[0], 0L));
      return out;
    }

    final long[][] norm = new long[n][CRITERIA];
    for (int j = 0; j < CRITERIA; j++) {
      final long[] col = new long[n];
      for (int k = 0; k < n; k++) {
        col[k] = rawWad[k][j];
      }
      final long[] normed = normaliseWad(col, j == LATENCY);
      for (int k = 0; k < n; k++) {
        norm[k][j] = normed[k];
      }
    }

    final long[] w = criticWeightsWad(norm);

    // Diagnostic: dump the exact inputs each node scored on. If two nodes disagree on the
    // proposer, one of these fields differs, and this names which.
    if (upToBlock % 5 == 0) {
      final StringBuilder sb = new StringBuilder();
      sb.append("CBBFT-RAW seq=").append(upToBlock).append(" nvals=").append(n)
        .append(" window=").append(window).append(" |");
      for (final Map.Entry<Address, Attr> e : attrs.entrySet()) {
        final Attr a = e.getValue();
        sb.append(' ').append(e.getKey().toString(), 0, 8)
          .append(":p=").append(a.proposed)
          .append(",s=").append(a.seals)
          .append(",g=").append(a.gasWadSum)
          .append(",l=").append(a.latencySecSum)
          .append('/').append(a.latencySamples);
      }
      sb.append(" | w=");
      for (int j = 0; j < CRITERIA; j++) {
        sb.append(w[j]).append(',');
      }
      LOG.info(sb.toString());
    }

    for (int k = 0; k < n; k++) {
      long f = 0;
      for (int j = 0; j < CRITERIA; j++) {
        f += wmul(norm[k][j], w[j]);
      }
      out.add(new Scored(ids[k], round4Wad(f)));
    }
    Collections.sort(out);
    return out;
  }

  /**
   * Split the scored validators into clusters at the first gap exceeding T = mean + 0.5 * sigma of
   * the consecutive F-score gaps. Simple path only: at n=15 this reliably yields several clusters,
   * so the coefficient cascade and array-split fallbacks in cbbft_engine.py are not reachable here
   * and are not implemented. Operates on the already-sorted list, so it is deterministic.
   *
   * @param scored validators sorted by F descending
   * @return index boundaries where a new cluster starts, always including 0
   */
  private static List<Integer> clusterBoundaries(final List<Scored> scored) {
    final List<Integer> starts = new ArrayList<>();
    starts.add(0);
    final int n = scored.size();
    if (n < 3) {
      return starts;
    }

    final long[] gaps = new long[n - 1];
    long sum = 0;
    for (int i = 0; i < n - 1; i++) {
      gaps[i] = scored.get(i).f - scored.get(i + 1).f;
      sum += gaps[i];
    }
    final long mean = sum / gaps.length;
    long acc = 0;
    for (final long g : gaps) {
      final long d = g - mean;
      acc += wmul(d, d);
    }
    final long sigma = wsqrt(acc / gaps.length);
    final long t = mean + sigma / 2;

    for (int i = 0; i < n - 1; i++) {
      if (gaps[i] > t) {
        starts.add(i + 1);
      }
    }
    return starts;
  }

  /**
   * Choose the proposer from the top cluster's candidate pool. The pool is the top 30 percent of the
   * cluster with a floor of three, and the round number indexes into it so a failed proposer is
   * followed by the next candidate rather than a repeat.
   *
   * @param scored validators sorted by F descending
   * @param round the round number within this sequence
   * @return the elected proposer
   */
  private static Address selectFromPool(
      final List<Scored> scored, final long sequence, final int round) {
    final List<Integer> starts = clusterBoundaries(scored);
    final int clusterEnd = starts.size() > 1 ? starts.get(1) : scored.size();

    // Floor of three is clamped against the whole validator set, not the top cluster. Clamping
    // against the cluster collapses the pool to one whenever the leader separates from the pack,
    // which then feeds back: sole proposer -> higher proposal count -> wider gap -> sole proposer.
    final int poolSize =
        Math.min(scored.size(), Math.max(3, (int) Math.ceil(clusterEnd * 0.30)));

    // Rotate on sequence as well as round, so proposal duty circulates within the pool instead of
    // resting on its top member. Both values are agreed by every node before the round begins.
    final int idx = Math.floorMod(sequence + round, poolSize);
    return scored.get(idx).id;
  }

  /** Round to 4 decimal places, matching Python round(x, 4) before clustering. */
  private static long round4Wad(final long x) {
    final long q = WAD / 10_000L;
    return x >= 0 ? ((x + q / 2) / q) * q : ((x - q / 2) / q) * q;
  }




  @Override
  public Address selectProposerForRound(final ConsensusRoundIdentifier roundIdentifier) {

    final long sequence = roundIdentifier.getSequenceNumber();
    final List<Scored> scored = computeScores(sequence);
    final Address proposer;
    if (scored.size() < 3 || sequence <= WINDOW) {
      // Not enough history for the attributes to mean anything - fall back to round robin so the
      // chain starts cleanly. Every node applies the same rule at the same height.
      LOG.info(
          "CBBFT-FALLBACK seq={} round={} scoredSize={}",
          sequence,
          roundIdentifier.getRoundNumber(),
          scored.size());
      proposer = delegate.selectProposerForRound(roundIdentifier);
    } else {
      proposer = selectFromPool(scored, sequence, roundIdentifier.getRoundNumber());
      LOG.info(
          "CBBFT-SELECT seq={} round={} proposer={} topF={}",
          sequence,
          roundIdentifier.getRoundNumber(),
          proposer,
          String.format("%.4f", (double) scored.get(0).f / WAD));
    }
    LOG.info("CBBFT selector active: {} proposer={}", roundIdentifier, proposer);
    return proposer;
  }
}
