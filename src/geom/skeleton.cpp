#pragma once

#include <iostream>
#include <cstddef> 
#include <vector>
#include <array>
#include <algorithm>
#include <string>
#include <memory>

#include "../utils/vector.cpp"
#include "../utils/matrix.cpp"
#include "../utils/stream.cpp"
#include "../utils/hash.cpp"
#include "../utils/quaternion.cpp"
#include "../utils/errors.cpp"
#include "../utils/checked_binary.hpp"
#include <unordered_map>
#include <unordered_set>
#include "binary/skeleton.hpp"

namespace dsts::geom
{  
    class Bone {
        public:
            uint32_t name_hash = 0;
            std::string name;

            binary::BoneTransform transform;
            
            std::shared_ptr<Bone> parent;

            bool is_geometry = false;

            void setName(std::string newName){
                name = newName;
                name_hash = crc32((const uint8_t*)name.data(),name.length());
            }
    };

    // Preserve native binding metadata without guessing how a target consumes it.
    struct FloatChannel {
        uint32_t name_hash = 0;
        uint32_t array_index = 0;
        uint8_t flags = 0;
    };

    class Skeleton {
        std::vector<std::array<uint16_t,2>> sourceParentPairs;
        std::vector<std::array<uint16_t,2>> sourceParentPadding;
        std::vector<uint16_t> sourceParentTable;
        std::vector<int> sourceParents;
        bool hasSourceParents=false;

        std::vector<int> parentIndices() const {
            std::vector<int> result;
            result.reserve(bones.size());
            for(const auto& bone:bones) result.push_back(bone->parent ? getIndex(bones,bone->parent) : -1);
            return result;
        }
        public:
            std::vector<std::shared_ptr<Bone>> bones;
            std::vector<FloatChannel> float_channels;

            bool allParentsValid() const {
                for (const auto& bone : bones) {
                    if (!bone) continue; // ignore null entries

                    if (bone->parent) {
                        // Check if parent is in the skeleton's bone list
                        bool found = false;
                        for (const auto& candidate : bones) {
                            if (candidate == bone->parent) {
                                found = true;
                                break;
                            }
                        }
                        if (!found) return false;
                    }
                }
                return true; // all parents either null or in bones
            }

            void validate() const {
                if (bones.size() > 0x7FFF) throw std::runtime_error("Skeleton has too many bones for its parent encoding");
                if (float_channels.size() > 65535) throw std::runtime_error("Skeleton has too many float channels");
                std::unordered_map<const Bone*, size_t> lookup;
                for (size_t i=0; i<bones.size(); ++i) {
                    if (!bones[i] || !lookup.emplace(bones[i].get(),i).second)
                        throw std::runtime_error("Skeleton contains a null or duplicate bone");
                }
                std::vector<int> parents(bones.size(),-1);
                for (size_t i=0; i<bones.size(); ++i) {
                    const auto& bone=bones[i];
                    if (bone->parent) {
                        const auto found=lookup.find(bone->parent.get());
                        if(found==lookup.end()) throw std::runtime_error("Bone parent is outside the skeleton");
                        parents[i]=static_cast<int>(found->second);
                    }
                    for(const float* values : {bone->transform.position,bone->transform.quaternion,bone->transform.scale})
                        for(int j=0;j<4;++j) if(!std::isfinite(values[j])) throw std::runtime_error("Bone transform is not finite");
                }
                validateParentIndices(parents);
            }

            static void validateParentIndices(const std::vector<int>& parents) {
                std::vector<uint8_t> state(parents.size(),0);
                for(size_t start=0;start<parents.size();++start) {
                    if(state[start]) continue;
                    int current=static_cast<int>(start);
                    while(current>=0 && state[current]==0) {
                        state[current]=1; current=parents[current];
                    }
                    if(current>=0 && state[current]==1) throw std::runtime_error("Skeleton parent cycle");
                    current=static_cast<int>(start);
                    while(current>=0 && state[current]==1) {state[current]=2;current=parents[current];}
                }
            }

            void read(std::istream& f, uint64_t skeleton_base = 0, uint64_t base = 0) {
                const auto origin=dsts::checkedAdd(base,skeleton_base,"Skeleton base");
                dsts::CheckedBinary input(f,origin);
                const auto header=input.object<binary::SkeletonHeader>(0,"Skeleton header");
                if(std::memcmp(header.magic,"60SE",4)!=0) throw std::runtime_error("Unsupported skeleton magic");
                if(header.bone_count>0x7FFF) throw std::runtime_error("Unsupported skeleton parent encoding");
                input.range(0,header.skeleton_file_size,1,"Skeleton size");
                if(header.skeleton_file_size<sizeof(header)) throw std::runtime_error("Invalid skeleton size");
                input.limit(header.skeleton_file_size,"Skeleton size");
                if(header.bone_count && header.bone_parent_vector_size!=2)
                    throw std::runtime_error("Unsupported bone parent vector size");
                // Native 140364850 consumes ceil(pair_count/4) SIMD groups,
                // including physical records beyond a non-multiple count.
                // Keep that tail for unchanged forensic/native imports.
                const uint64_t physicalPairCount=(uint64_t(header.bone_parent_pairs_count)+3)&~uint64_t(3);
                auto physicalPairs=input.array<std::array<uint16_t,2>>(sizeof(header),physicalPairCount,"Physical bone parent pairs");
                std::vector<std::array<uint16_t,2>> pairs(physicalPairs.begin(),physicalPairs.begin()+header.bone_parent_pairs_count);
                std::vector<std::array<uint16_t,2>> pairPadding(physicalPairs.begin()+header.bone_parent_pairs_count,physicalPairs.end());
                auto transforms=input.array<binary::BoneTransform>(dsts::checkedAdd(header.bone_transform_offset,
                    offsetof(binary::SkeletonHeader,bone_transform_offset),"Bone transforms"),header.bone_count,"Bone transforms");
                auto hashes=input.array<uint32_t>(dsts::checkedAdd(header.bone_name_hashes_offset,
                    offsetof(binary::SkeletonHeader,bone_name_hashes_offset),"Bone hashes"),header.bone_count,"Bone hashes");
                auto table=input.array<uint16_t>(dsts::checkedAdd(header.parent_bones_offset,
                    offsetof(binary::SkeletonHeader,parent_bones_offset),"Parent indices"),header.bone_count,"Parent indices");
                std::vector<FloatChannel> channels;
                if(header.float_channel_count) {
                    if(!header.float_channel_array_indices_offset || !header.float_channel_name_hashes_offset || !header.float_channel_flags_offset)
                        throw std::runtime_error("Float channel table has a null offset");
                    auto indices=input.array<uint32_t>(dsts::checkedAdd(header.float_channel_array_indices_offset,
                        offsetof(binary::SkeletonHeader,float_channel_array_indices_offset),"Float channel indices"),header.float_channel_count,"Float channel indices");
                    auto channelHashes=input.array<uint32_t>(dsts::checkedAdd(header.float_channel_name_hashes_offset,
                        offsetof(binary::SkeletonHeader,float_channel_name_hashes_offset),"Float channel hashes"),header.float_channel_count,"Float channel hashes");
                    auto flags=input.array<uint8_t>(dsts::checkedAdd(header.float_channel_flags_offset,
                        offsetof(binary::SkeletonHeader,float_channel_flags_offset),"Float channel flags"),header.float_channel_count,"Float channel flags");
                    channels.resize(header.float_channel_count);
                    for(size_t i=0;i<channels.size();++i) channels[i]={channelHashes[i],indices[i],flags[i]};
                }
                std::vector<int> parents(header.bone_count,-1);
                std::vector<bool> seen(header.bone_count,false);
                for(auto index:table) {
                    if(index>=pairs.size()) throw std::runtime_error("Bone parent pair index is out of range");
                    auto bone=pairs[index][0], parent=pairs[index][1];
                    // Native 0x1402E2C90 masks the high bit before parent lookup.
                    parent &= 0x7FFF;
                    if(bone>=header.bone_count || (parent!=0x7FFF && parent>=header.bone_count))
                        throw std::runtime_error("Bone or parent index is out of range");
                    if(seen[bone]) throw std::runtime_error("Duplicate bone parent assignment");
                    seen[bone]=true;parents[bone]=parent==0x7FFF ? -1 : parent;
                }
                validateParentIndices(parents);
                std::vector<std::shared_ptr<Bone>> parsed;
                parsed.reserve(header.bone_count);
                for(size_t i=0;i<header.bone_count;++i) {
                    auto bone=std::make_shared<Bone>();bone->transform=transforms[i];bone->name_hash=hashes[i];parsed.push_back(bone);
                }
                for(size_t i=0;i<parsed.size();++i) if(parents[i]>=0) parsed[i]->parent=parsed[parents[i]];
                bones=std::move(parsed);float_channels=std::move(channels);validate();
                sourceParentPairs=std::move(pairs);sourceParentPadding=std::move(pairPadding);sourceParentTable=std::move(table);
                sourceParents=std::move(parents);hasSourceParents=true;
            }

            uint64_t write(std::ostream& f, int skeleton_base = 0, int base = 0) {
                if(base<0 || skeleton_base<0) throw std::runtime_error("Negative skeleton base");
                validate();
                f.exceptions(std::ios::failbit | std::ios::badbit);
                binary::SkeletonHeader header{};
                f.seekp(static_cast<uint64_t>(skeleton_base) + static_cast<uint64_t>(base));
                alignStream(f, 0x10);
                uint64_t skeleton_start = f.tellp();

                header.bone_count = bones.size();
                header.float_channel_count = float_channels.size();
                header.bone_parent_pairs_count = bones.size();
                header.bone_parent_vector_size = 2;

                std::vector<std::array<uint16_t, 2>> bone_parent_pairs(bones.size());
                std::vector<uint16_t> parent_bones(bones.size());
                std::vector<binary::BoneTransform> transforms(bones.size());
                std::vector<uint32_t> bone_name_hashes(bones.size());
                for (int i = 0; i < bones.size() ;i++) {

                    std::array<uint16_t, 2> vector;
                    vector[0] = i;
                    if (bones[i]->parent) {
                        uint16_t parent_index = getIndex(bones, bones[i]->parent);
                        vector[1] = parent_index;
                    } else {
                        constexpr uint16_t NoParent = 0x7FFF;
                        vector[1] = NoParent;
                    }
                    bone_parent_pairs[i] = vector;
                    parent_bones[i] = i;

                    transforms[i] = bones[i]->transform;
                    if (bones[i]->name.length() > 0) {
                        bone_name_hashes[i] = crc32((const uint8_t *)(bones[i]->name.c_str()),bones[i]->name.length());
                    } else {
                        bone_name_hashes[i] = bones[i]->name_hash;
                    }
                }

                if(hasSourceParents && sourceParents==parentIndices()) {
                    bone_parent_pairs=sourceParentPairs;
                    parent_bones=sourceParentTable;
                    header.bone_parent_pairs_count=bone_parent_pairs.size();
                    bone_parent_pairs.insert(bone_parent_pairs.end(),sourceParentPadding.begin(),sourceParentPadding.end());
                } else {
                    const auto flagged=[](const auto& pair){return (pair[1]&0x8000)!=0;};
                    if(hasSourceParents && (std::any_of(sourceParentPairs.begin(),sourceParentPairs.end(),flagged)
                            || std::any_of(sourceParentPadding.begin(),sourceParentPadding.end(),flagged)))
                        throw std::runtime_error("Changing a flagged skeleton hierarchy is not supported");
                    // Padding with zero bytes creates self-parent (0,0)
                    // evaluations which overwrite the owner's root transform.
                    // Native one-bone t0109traffic01d/e use four (0,0x7FFF)
                    // records and count4. Repeat the final valid pair: its
                    // distinct parent (or owner sentinel) is unchanged, making
                    // the repeated assignment idempotent.
                    if(!bone_parent_pairs.empty()) {
                        const auto last=bone_parent_pairs.back();
                        bone_parent_pairs.resize((bone_parent_pairs.size()+3)&~size_t(3),last);
                    }
                    header.bone_parent_pairs_count=bone_parent_pairs.size();
                }

                f.seekp(skeleton_start+sizeof(binary::SkeletonHeader));
                f.write(reinterpret_cast<char*>(bone_parent_pairs.data()), sizeof(uint16_t) * 2 * bone_parent_pairs.size());

                alignStream(f, 0x10);
                header.bone_transform_offset = (uint64_t)(f.tellp()) - (skeleton_start + offsetof(binary::SkeletonHeader, bone_transform_offset));
                f.write(reinterpret_cast<char*>(transforms.data()), sizeof(binary::BoneTransform) * transforms.size());

                alignStream(f, 0x10);
                header.parent_bones_offset = (uint64_t)(f.tellp()) - (skeleton_start + offsetof(binary::SkeletonHeader, parent_bones_offset));
                f.write(reinterpret_cast<char*>(parent_bones.data()), sizeof(uint16_t) * parent_bones.size());

                // Captured 60SE layout: byte flags follow the parent indices;
                // the hash section contains bone hashes, float indices, hashes.
                alignStream(f, 0x4);
                header.float_channel_flags_offset = static_cast<uint64_t>(f.tellp()) -
                    (skeleton_start + offsetof(binary::SkeletonHeader,float_channel_flags_offset));
                for(const auto& channel:float_channels) f.write(reinterpret_cast<const char*>(&channel.flags),sizeof(channel.flags));

                alignStream(f, 0x10);
                uint64_t hashes_section_start = f.tellp();
                header.bone_name_hashes_offset = (uint64_t)(f.tellp()) - (skeleton_start + offsetof(binary::SkeletonHeader, bone_name_hashes_offset));
                f.write(reinterpret_cast<char*>(bone_name_hashes.data()), sizeof(uint32_t) * bone_name_hashes.size());
                header.float_channel_array_indices_offset = static_cast<uint64_t>(f.tellp()) -
                    (skeleton_start + offsetof(binary::SkeletonHeader,float_channel_array_indices_offset));
                for(const auto& channel:float_channels) f.write(reinterpret_cast<const char*>(&channel.array_index),sizeof(channel.array_index));
                header.float_channel_name_hashes_offset = static_cast<uint64_t>(f.tellp()) -
                    (skeleton_start + offsetof(binary::SkeletonHeader,float_channel_name_hashes_offset));
                for(const auto& channel:float_channels) f.write(reinterpret_cast<const char*>(&channel.name_hash),sizeof(channel.name_hash));
                
                uint64_t before_pad = f.tellp();
                alignStream(f, 0x10);
                if (before_pad < f.tellp()) {
                    f.seekp((uint64_t)(f.tellp())-0x1);
                    char zero = '\0';
                    f.write(&zero,0x1);
                }
                uint64_t skeleton_end = f.tellp();

                header.skeleton_file_size = skeleton_end - skeleton_start;
                header.hashes_section_bytecount = skeleton_end - hashes_section_start;

                f.seekp(skeleton_start);
                f.write(reinterpret_cast<char*>(&header), sizeof(binary::SkeletonHeader));

                return header.skeleton_file_size;
            }
    };
    
    binary::Ibpm ibpmFromMatrix(Matrix matrix) {
        binary::Ibpm ibpm;
        ibpm.matrix[0] = matrix(0,0);
        ibpm.matrix[1] = matrix(0,1);
        ibpm.matrix[2] = matrix(0,2);
        ibpm.matrix[3] = matrix(0,3);

        ibpm.matrix[4] = matrix(1,0);
        ibpm.matrix[5] = matrix(1,1);
        ibpm.matrix[6] = matrix(1,2);
        ibpm.matrix[7] = matrix(1,3);

        ibpm.matrix[8] = matrix(2,0);
        ibpm.matrix[9] = matrix(2,1);
        ibpm.matrix[10] = matrix(2,2);
        ibpm.matrix[11] = matrix(2,3);
        return ibpm;
    }

    Matrix MatrixFromIbpm(binary::Ibpm ibpm) {
        Matrix matrix;
        matrix(0,0) = ibpm.matrix[0];
        matrix(0,1) = ibpm.matrix[1];
        matrix(0,2) = ibpm.matrix[2];
        matrix(0,3) = ibpm.matrix[3];

        matrix(1,0) = ibpm.matrix[4];
        matrix(1,1) = ibpm.matrix[5];
        matrix(1,2) = ibpm.matrix[6];
        matrix(1,3) = ibpm.matrix[7];

        matrix(2,0) = ibpm.matrix[8];
        matrix(2,1) = ibpm.matrix[9];
        matrix(2,2) = ibpm.matrix[10];
        matrix(2,3) = ibpm.matrix[11];
        return matrix;
    }

    binary::BoneTransform DecomposeMatrix(const Matrix& mat) {
        binary::BoneTransform bt;

        // Extract translation
        bt.position[0] = mat(0,3);
        bt.position[1] = mat(1,3);
        bt.position[2] = mat(2,3);
        bt.position[3] = 1.0f;

        // Extract scale
        float scaleX = std::sqrt(mat(0,0)*mat(0,0) + mat(1,0)*mat(1,0) + mat(2,0)*mat(2,0));
        float scaleY = std::sqrt(mat(0,1)*mat(0,1) + mat(1,1)*mat(1,1) + mat(2,1)*mat(2,1));
        float scaleZ = std::sqrt(mat(0,2)*mat(0,2) + mat(1,2)*mat(1,2) + mat(2,2)*mat(2,2));

        bt.scale[0] = scaleX;
        bt.scale[1] = scaleY;
        bt.scale[2] = scaleZ;
        bt.scale[3] = 1.0f;

        // Remove scale from rotation matrix
        float rot[3][3];
        rot[0][0] = mat(0,0) / scaleX;
        rot[0][1] = mat(0,1) / scaleY;
        rot[0][2] = mat(0,2) / scaleZ;

        rot[1][0] = mat(1,0) / scaleX;
        rot[1][1] = mat(1,1) / scaleY;
        rot[1][2] = mat(1,2) / scaleZ;

        rot[2][0] = mat(2,0) / scaleX;
        rot[2][1] = mat(2,1) / scaleY;
        rot[2][2] = mat(2,2) / scaleZ;

        // Convert rotation matrix to quaternion
        float trace = rot[0][0] + rot[1][1] + rot[2][2];
        if(trace > 0) {
            float s = 0.5f / std::sqrt(trace + 1.0f);
            bt.quaternion[3] = 0.25f / s;
            bt.quaternion[0] = (rot[2][1] - rot[1][2]) * s;
            bt.quaternion[1] = (rot[0][2] - rot[2][0]) * s;
            bt.quaternion[2] = (rot[1][0] - rot[0][1]) * s;
        } else {
            if(rot[0][0] > rot[1][1] && rot[0][0] > rot[2][2]) {
                float s = 2.0f * std::sqrt(1.0f + rot[0][0] - rot[1][1] - rot[2][2]);
                bt.quaternion[3] = (rot[2][1] - rot[1][2]) / s;
                bt.quaternion[0] = 0.25f * s;
                bt.quaternion[1] = (rot[0][1] + rot[1][0]) / s;
                bt.quaternion[2] = (rot[0][2] + rot[2][0]) / s;
            } else if(rot[1][1] > rot[2][2]) {
                float s = 2.0f * std::sqrt(1.0f + rot[1][1] - rot[0][0] - rot[2][2]);
                bt.quaternion[3] = (rot[0][2] - rot[2][0]) / s;
                bt.quaternion[0] = (rot[0][1] + rot[1][0]) / s;
                bt.quaternion[1] = 0.25f * s;
                bt.quaternion[2] = (rot[1][2] + rot[2][1]) / s;
            } else {
                float s = 2.0f * std::sqrt(1.0f + rot[2][2] - rot[0][0] - rot[1][1]);
                bt.quaternion[3] = (rot[1][0] - rot[0][1]) / s;
                bt.quaternion[0] = (rot[0][2] + rot[2][0]) / s;
                bt.quaternion[1] = (rot[1][2] + rot[2][1]) / s;
                bt.quaternion[2] = 0.25f * s;
            }
        }

        return bt;
    }

    Matrix TransformToMatrix(const binary::BoneTransform& t){
        float x = t.quaternion[0];
        float y = t.quaternion[1];
        float z = t.quaternion[2];
        float w = t.quaternion[3];

        float xx = x*x, yy = y*y, zz = z*z;
        float xy = x*y, xz = x*z, yz = y*z;
        float wx = w*x, wy = w*y, wz = w*z;

        Matrix m;

        m(0,0) = (1 - 2*(yy + zz)) * t.scale[0];
        m(0,1) = (2*(xy - wz)) * t.scale[0];
        m(0,2) = (2*(xz + wy)) * t.scale[0];
        m(0,3) = t.position[0];

        m(1,0) = (2*(xy + wz)) * t.scale[1];
        m(1,1) = (1 - 2*(xx + zz)) * t.scale[1];
        m(1,2) = (2*(yz - wx)) * t.scale[1];
        m(1,3) = t.position[1];

        m(2,0) = (2*(xz - wy)) * t.scale[2];
        m(2,1) = (2*(yz + wx)) * t.scale[2];
        m(2,2) = (1 - 2*(xx + yy)) * t.scale[2];
        m(2,3) = t.position[2];

        m(3,0) = 0;
        m(3,1) = 0;
        m(3,2) = 0;
        m(3,3) = 1;

        return m;
    }

    Matrix GetWorldMatrix(const Bone &bone){
        std::vector<const Bone*> chain;
        std::unordered_set<const Bone*> seen;
        for(const Bone* current=&bone;current;current=current->parent.get()) {
            if(!seen.insert(current).second) throw std::runtime_error("Skeleton parent cycle");
            chain.push_back(current);
        }
        Matrix result=TransformToMatrix(chain.back()->transform);
        for(auto i=chain.rbegin()+1;i!=chain.rend();++i)
            result=result.multiply(TransformToMatrix((*i)->transform));
        return result;
    }

    Matrix GetWorldMatrix(const std::shared_ptr<Bone>& bone){
        if(!bone) throw std::runtime_error("Null bone has no world transform");
        return GetWorldMatrix(*bone);
    }

    Matrix ComputeInverseBindPose(const std::shared_ptr<Bone>& bone){
        Matrix world = GetWorldMatrix(bone);
        return world.inverse();
    }

    Matrix ComputeInverseBindPose(const Bone &bone){
        Matrix world = GetWorldMatrix(bone);
        return world.inverse();
    }

    // Absolute transform: parent + relative
    binary::BoneTransform getAbsoluteTransform(const binary::BoneTransform &rel, const binary::BoneTransform *parent) {
        binary::BoneTransform out = rel;
        if (!parent) return out;

        // Quaternion
        quat_mul(parent->quaternion, rel.quaternion, out.quaternion);

        // Scale (component-wise)
        for (int i = 0; i < 3; ++i)
            out.scale[i] = parent->scale[i] * rel.scale[i];
        out.scale[3] = 1.0f;

        // Position: parent_position + rotated & scaled child position
        float scaled[3] = { rel.position[0]*parent->scale[0], rel.position[1]*parent->scale[1], rel.position[2]*parent->scale[2] };
        quat_rotate(parent->quaternion, scaled, out.position);
        out.position[0] += parent->position[0];
        out.position[1] += parent->position[1];
        out.position[2] += parent->position[2];
        out.position[3] = 1.0f;

        return out;
    }

    // Relative transform: absolute - parent
    binary::BoneTransform getRelativeTransform(const binary::BoneTransform &abs, const binary::BoneTransform *parent) {
        binary::BoneTransform out = abs;
        if (!parent) return out;

        // Quaternion
        float inv[4];
        quat_inverse(parent->quaternion, inv);
        quat_mul(inv, abs.quaternion, out.quaternion);

        // Scale (component-wise)
        for (int i = 0; i < 3; ++i)
            out.scale[i] = abs.scale[i] / parent->scale[i];
        out.scale[3] = 1.0f;

        // Position: inverse rotate & scale
        float pos[3] = { abs.position[0] - parent->position[0],
                        abs.position[1] - parent->position[1],
                        abs.position[2] - parent->position[2] };
        quat_rotate(inv, pos, pos);
        for (int i = 0; i < 3; ++i) pos[i] /= parent->scale[i];
        out.position[0] = pos[0];
        out.position[1] = pos[1];
        out.position[2] = pos[2];
        out.position[3] = 1.0f;

        return out;
    }

    bool transformEqual(const binary::BoneTransform& a,
                        const binary::BoneTransform& b,
                        float eps = 1e-4f)
    {
        // --- Quaternion comparison (q ≈ b or q ≈ -b) ---
        float dot = 0.0f;
        for (int i = 0; i < 4; ++i)
            dot += a.quaternion[i] * b.quaternion[i];

        // normalize dot tolerance to unit quaternions:
        // |dot| should be close to 1 for equivalent rotations
        if (std::fabs(1.0f - std::fabs(dot)) > eps)
            return false;

        // --- Position comparison ---
        for (int i = 0; i < 4; ++i)
            if (std::fabs(a.position[i] - b.position[i]) > eps)
                return false;

        // --- Scale comparison ---
        for (int i = 0; i < 4; ++i)
            if (std::fabs(a.scale[i] - b.scale[i]) > eps)
                return false;

        return true;
    }

    bool ibpmEqual(const binary::Ibpm& a, const binary::Ibpm& b, float eps = 1e-4f) {
        for (int i = 0; i < 12; ++i) {
            if (std::fabs(a.matrix[i] - b.matrix[i]) > eps) {
                return false;
            }
        }
        return true;
    }

    std::string printTransform(binary::BoneTransform b) {
        std::ostringstream oss;
        oss << "quat :" << b.quaternion[0] << " " << b.quaternion[1] << " " << b.quaternion[2] << " " << b.quaternion[3] << std::endl;
        oss << "pos  :" <<b.position[0] << " " << b.position[1] << " " << b.position[2] << " " << b.position[3] << std::endl;
        oss << "scale:" << b.scale[0] << " " << b.scale[1] << " " << b.scale[2] << " " << b.scale[3];
        return oss.str();
    }
}
