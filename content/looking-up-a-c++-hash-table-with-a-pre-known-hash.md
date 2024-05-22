Title: Looking up a C++ Hash Table with a pre-known hash
Date: 2024-05-22
Category: C++
Tags: C++
Summary: Speed up your repeated hash table searches with this one neat trick!

# A recap of associative containers in C++

Associative containers allow for fast insertion, deletion, and most importantly search of elements.  
The C++ standard library has provided associative containers since the beginning, but as with all things in C++, life wasn't always great.

I don't intend to go over all the details, so here's a quick overview:

* C++98: [`std::set`](https://en.cppreference.com/w/cpp/container/set), [`std::multiset`](https://en.cppreference.com/w/cpp/container/multiset), [`std::map`](https://en.cppreference.com/w/cpp/container/map), [`std::multimap`](https://en.cppreference.com/w/cpp/container/multimap)
* C++11: [`std::unordered_set`](https://en.cppreference.com/w/cpp/container/unordered_set), [`std::unordered_multiset`](https://en.cppreference.com/w/cpp/container/unordered_multiset), [`std::unordered_map`](https://en.cppreference.com/w/cpp/container/unordered_map), [`std::unordered_multimap`](https://en.cppreference.com/w/cpp/container/unordered_multimap) - sacrifice ordered iteration for (usually) even faster operations
* C++14: Heterogeneous lookup for [`std::set`](https://en.cppreference.com/w/cpp/container/set) and [`std::map`](https://en.cppreference.com/w/cpp/container/map) - [N3657](https://wg21.link/n3657)
* C++20: Heterogeneous lookup for [`std::unordered_set`](https://en.cppreference.com/w/cpp/container/unordered_set) and [`std::unordered_map`](https://en.cppreference.com/w/cpp/container/unordered_map) - [P0919R3](https://wg21.link/P0919R3)

[`std::unordered_set`](https://en.cppreference.com/w/cpp/container/unordered_set) and [`std::unordered_map`](https://en.cppreference.com/w/cpp/container/unordered_map) are by far the most important and most used of the bunch, and the rest of this article is exclusively about them.

# Heterogeneous lookup

The initial function signatures for unordered container lookup were pretty simple, take for example [`find`](https://en.cppreference.com/w/cpp/container/unordered_set/find):

```cpp
template<typename T>
std::unordered_set<T>::iterator std::unordered_set<T>::find(const T &key);
```

However, simple isn't always best - this requires always constructing an instance of `T`. The most common culprit is

```cpp
std::unordered_set<std::string> my_set;
my_set.erase("foo");
```

This constructs a temporary [`std::string`](https://en.cppreference.com/w/cpp/string/basic_string) from the string literal, which is of course unnecessary as [`std::string`](https://en.cppreference.com/w/cpp/string/basic_string) can compare to literals directly.

The common solution is to use heterogeneous lookup as described in [P0919R3](https://wg21.link/P0919R3):

```cpp
struct StringHash {
    using is_transparent = void; // Enables heterogeneous operations.

    std::size_t operator()(std::string_view sv) const {
        return std::hash<std::string_view>{}(sv);
    }
};

void example() {
    std::unordered_set<std::string, StringHash, std::equal_to<>> my_set;

    // Converts "foo" to string_view and uses it for hash and compare.
    my_set.erase("foo");
}
```

Usage of non-heterogeneous associative string containers is also [diagnosed by SonarLint](https://rules.sonarsource.com/cpp/RSPEC-6045/).

However, there is another neat trick you can do, one that I haven't seen mentioned but can be quite helpful in some situations:  
**The transparent hash (and equality predicate) operators do not have to consume a type that is convertible to the key type.**

# Passing a hash to the heterogeneous lookup

And with that we get to today's big revelation: With heterogeneous lookup, you can pass a known hash directly!  
This is helpful when you need to find an object in one of multiple sets. Where before each set would recompute the hash for itself, which can be quite expensive relative to the lookup, now you can just precompute the hash once and pass it to the lookup functions!

```cpp
using key_hash_pair = std::tuple<std::string_view, std::size_t>;

struct Hash {
    using is_transparent = void;

    std::size_t operator()(std::string_view sv) const {
        return std::hash<std::string_view>{}(sv);
    }
    std::size_t operator()(key_hash_pair pair) const {
        return std::get<1>(pair);
    }
};

struct Pred {
    using is_transparent = void;

    bool operator()(std::string_view lhs, std::string_view rhs) const {
        return lhs == rhs;
    }
    bool operator()(key_hash_pair lhs, std::string_view rhs) const {
        return std::get<0>(lhs) == rhs;
    }
};

using Set = std::unordered_set<std::string, Hash, Pred>;

int main() {
    Set set{"foo"};

    const std::string string{"foo"};
    const std::size_t hash{std::hash<std::string>{}(string)};
    const key_hash_pair pair{string, hash};

    assert(set.contains(pair));
}
```

There's one issue with this - nothing prevents us from passing a hash from a different hash function, or reusing the pair with a set of different hash type, or just passing some bogus integer!  
A better approach would be to use a rich type for `key_hash_pair` that takes care of this, such as

```cpp
template<typename Hash>
class KeyHashPair {
private:
    std::string_view key_;
    std::size_t hash_;
public:
    KeyHashPair() = delete;
    KeyHashPair(std::string_view sv) : key_(sv), hash_(Hash{}(key_)) {}

    std::string_view key() const { return key_; }
    std::size_t hash() const { return hash_; }
};

struct Hash {
    using is_transparent = void;

    std::size_t operator()(std::string_view sv) const {
        return std::hash<std::string_view>{}(sv);
    }
    std::size_t operator()(KeyHashPair<Hash> pair) const {
        return pair.hash();
    }
};

struct Pred {
    using is_transparent = void;

    bool operator()(std::string_view lhs, std::string_view rhs) const {
        return lhs == rhs;
    }
    template<typename Hash>
    bool operator()(KeyHashPair<Hash> lhs, std::string_view rhs) const {
        return lhs.key() == rhs;
    }
};

using Set = std::unordered_set<std::string, Hash, Pred>;

int main() {
    Set set{"foo"};

    const std::string string{"foo"};
    const KeyHashPair<Set::hasher> pair{string};

    assert(set.contains(pair));
}
```

You can find a godbolt example [here](https://godbolt.org/z/je15e87z1).

# Closing remarks

Of course, this code is missing various decorators such as [`noexcept`](https://en.cppreference.com/w/cpp/language/noexcept_spec), [`[[nodiscard]]`](https://en.cppreference.com/w/cpp/language/attributes/nodiscard), passing by `const T&`, and the (highly recommended) [`[[clang::lifetimebound]]`](https://clang.llvm.org/docs/AttributeReference.html#lifetimebound).  
I shall leave that as an excercise for the reader.

The example makes use of [`std::string_view`](https://en.cppreference.com/w/cpp/string/basic_string_view), but of course the transparent hash lookup can also be used for types which themselves can not be meaningfully used in transparent comparisons.

Heterogeneous lookup is also supported by the (blazingly fast) unordered containers from [Boost.Unordered](https://www.boost.org/doc/libs/release/libs/unordered/).

Tangentially related, if you find yourself storing multiple copies of the same object in various sets, perhaps consider using the [Flyweight pattern](https://en.wikipedia.org/wiki/Flyweight_pattern) to reduce memory overhead, for example via the lovely [Boost.Flyweight](https://www.boost.org/doc/libs/release/libs/flyweight/).
